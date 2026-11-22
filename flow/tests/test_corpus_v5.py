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


if __name__ == '__main__':
    unittest.main()
