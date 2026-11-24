"""The production corpus must always pass the authoring validator and be wired into the knowledge graph."""
import unittest, tempfile, sys, json, os, io, contextlib
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, content_v50

VALIDATOR = ROOT / 'tools' / 'corpus_validate.py'


class CorpusV5Tests(unittest.TestCase):
    def test_every_file_passes_the_validator(self):
        if not VALIDATOR.exists():
            self.skipTest('validator only ships with the source repository')
        sys.path.insert(0, str(VALIDATOR.parent))
        import corpus_validate
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = corpus_validate.main([])
        self.assertEqual(code, 0, out.getvalue()[-3000:])

    def test_corpus_is_balanced_across_themes_and_levels(self):
        packs = content_v50.v5_materials()
        self.assertGreaterEqual(len(packs), 96)
        cells = {}
        for p in packs:
            cells[(p['theme'], p['cefr'])] = cells.get((p['theme'], p['cefr']), 0) + 1
        for theme in ('campus', 'travel', 'life', 'work', 'culture', 'science'):
            for cefr in ('A2', 'B1', 'B2', 'C1'):
                self.assertGreaterEqual(cells.get((theme, cefr), 0), 4, (theme, cefr))
        self.assertEqual(len({p['id'] for p in packs}), len(packs))
        self.assertTrue(all(p['level'] == ('B2' if p['cefr'] == 'C1' else p['cefr']) for p in packs))

    def test_corpus_is_seeded_and_linked_into_the_graph(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, 'DB', Path(tmp) / 'v5.db'):
            app.init()
            with app.db() as c:
                ids = {p['id'] for p in content_v50.v5_materials()}
                seeded = {r[0] for r in c.execute("SELECT id FROM lab_packs WHERE id LIKE 'v5-%'")}
                self.assertEqual(seeded, ids)
                __import__('lexicon_service').sync_packs(c)
                linked = {r[0][len('material:'):] for r in c.execute("SELECT target FROM kg_edges WHERE relation='practised_in' AND target LIKE 'material:v5-%'")}
                self.assertEqual(linked, ids)
                nodes = {r[0] for r in c.execute("SELECT source FROM kg_edges WHERE relation='practised_in' AND target LIKE 'material:v5-%'")}
                self.assertEqual(len(nodes), 18)
                quality = __import__('quality_service')
                for r in c.execute("SELECT * FROM lab_packs WHERE id LIKE 'v5-%'"):
                    self.assertTrue(quality.recommendable(c, r), r['id'])

    def test_additive_edits_reach_a_running_database(self):
        """lab_packs is written once: a third question or new tags in a file must still reach the site (v5 sync),
        earlier questions keep their place, review states carry over, and a changed text is never applied."""
        with tempfile.TemporaryDirectory() as tmp, patch.object(app, 'DB', Path(tmp) / 'sync.db'):
            app.init()
            packs = content_v50.v5_materials()
            a, b, d, e = (json.loads(json.dumps(x)) for x in packs[:4])
            with app.db() as c:
                c.execute('INSERT INTO material_reviews(pack,content_hash,status,checks,note,actor,created) VALUES(?,?,?,?,?,?,?)',
                          (a['id'], __import__('quality_service').digest(a), 'disabled', '{}', '停用测试', None, 0))
                c.commit()
            a['questions'].append({'prompt': 'What is the main point?', 'options': ['w', 'x', 'y', 'z'], 'answer': 0,
                                   'evidence': a['body'][:20], 'type': 'main'})
            a['questions'][0]['type'] = 'detail'
            a['purposes'] = ['story']
            b['body'] = b['body'] + ' Changed.'
            d['questions'] = d['questions'][::-1]
            e['questions'][0]['type'] = 'detail'
            e['questions'].append(dict(e['questions'][1], prompt='Which word fits?', type='main'))
            with patch.object(content_v50, 'v5_materials', return_value=[a, b, d, e] + packs[4:]):
                with app.db() as c:
                    self.assertEqual(content_v50.sync(c), [a['id'], e['id']])
                    got = json.loads(c.execute('SELECT content FROM lab_packs WHERE id=?', (a['id'],)).fetchone()[0])
                    self.assertEqual(len(got['questions']), len(packs[0]['questions']) + 1)
                    self.assertEqual(got['purposes'], ['story'])
                    row = c.execute('SELECT * FROM lab_packs WHERE id=?', (a['id'],)).fetchone()
                    self.assertEqual(__import__('quality_service').info(c, row)['status'], 'disabled')
                    self.assertNotIn('Changed.', json.loads(c.execute('SELECT content FROM lab_packs WHERE id=?', (b['id'],)).fetchone()[0])['body'])
                    self.assertEqual(content_v50.sync(c), [])
                    import next_service as nx
                    self.assertEqual(nx.material(c, None, a['id'])[1], 404)  # still disabled after the sync
                    m, code = nx.material(c, None, e['id'])
                    self.assertEqual(code, 200)
                    self.assertEqual(m['questions'][0].get('type'), '细节')
                    self.assertEqual(m['questions'][-1].get('type'), '主旨')

    def test_v51_rules(self):
        if not VALIDATOR.exists():
            self.skipTest('validator only ships with the source repository')
        sys.path.insert(0, str(VALIDATOR.parent))
        import corpus_validate as cv
        p = json.loads(json.dumps(next(x for x in content_v50.v5_materials() if x['cefr'] == 'C1')))
        p['spec'] = '5.1'
        p.pop('ai', None)
        p['questions'] = [{k: v for k, v in q.items() if k != 'type'} for q in p['questions'][:2]]
        E, _ = cv.check_v51(p, p['body'], {'sentences': 10})
        self.assertTrue(any('13 句' in e for e in E) and any('3–4 道题' in e for e in E) and any('AI 辅助编写' in e for e in E))
        p['ai'] = 'AI 辅助编写'
        p['questions'] = [dict(q, type=t) for q, t in zip(p['questions'] * 2, ('main', 'inference', 'vocab', 'detail'))]
        p['reviewed'] = True
        p['quotes'] = [{'text': p['body'][:15], 'author': 'X', 'work': 'Y', 'year': 1990, 'author_died': 2001}]
        p['references'] = [{'title': 'a', 'url': 'https://example.org'}]
        E, _ = cv.check_v51(p, p['body'], {'sentences': 14})
        self.assertTrue(any('人工审校' in e for e in E) and any('公有领域' in e for e in E) and any('核实日期' in e for e in E))
        del p['reviewed'], p['quotes'], p['references']
        self.assertEqual(cv.check_v51(p, p['body'], {'sentences': 14})[0], [])


if __name__ == '__main__':
    unittest.main()
