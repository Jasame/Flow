"""练习记录 (history_service): the records are made by the practice code itself (a model stands in), then read back,
paged, and deleted, for the learner's own rows only."""
import json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, skills_service as sk, history_service as hs, output_service as out

T0 = time.time() - 3 * 86400
END = {'summary': '说得清楚，点单顺利。', 'good': ['Could I have a latte, please?'],
       'fixes': [{'from': 'big one', 'to': 'a large one', 'why': '点大杯说 a large one', 'node': None}],
       'expressions': [{'text': 'Is it for here or to go?', 'meaning': '在这儿喝还是带走？'}], 'score': 0.78}


def fake(messages, audio=None, grounding=False):
    system, user = messages[0]['content'], messages[-1]['content']
    if '对话结束' in user:
        return json.dumps(fake.end), 'stop'
    if '开始对话' in user:
        return json.dumps({'scene': '你走进咖啡店。', 'role': '店员', 'reply': 'Hi! What can I get you?'}), 'stop'
    if '考官问了一个问题' in system:
        return json.dumps({'better': None, 'note': '流利'}), 'stop'
    if '雅思口语 Part 1 · 话题' in user:
        return json.dumps({'bands': {'fc': 6, 'lr': 6, 'gra': 6, 'p': None}, 'notes': {}, 'summary': '回答直接。',
                           'fixes': [{'from': 'I am study', 'to': 'I am studying', 'why': '进行时'}], 'model': 'I study law.', 'model_q': 1}), 'stop'
    if '"points"' in user or 'points' in system:
        return json.dumps({'points': [{'point': '主角', 'covered': True}, {'point': '结局', 'covered': False}], 'used': [],
                           'fixes': [{'from': 'he goed', 'to': 'he went', 'why': '过去式'}], 'comment': '要点讲到一半。', 'model': ''}), 'stop'
    return json.dumps({'reply': 'Sure. Anything else?', 'correction': None, 'hint': ''}), 'stop'


fake.end = END
REWRITE = {'verdict': 'minor', 'summary': '意思清楚，时态需要统一。', 'corrected': 'If I had left earlier, I would have caught the bus.',
           'changes': [{'from': 'would catch', 'to': 'would have caught', 'why': '与过去事实相反要用 would have done'}],
           'versions': [{'label': '更自然', 'text': 'Had I left earlier, I would have made the bus.', 'why': '倒装更紧凑'}],
           'keep': {'text': 'make the bus', 'meaning': '赶上公交'}}


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'h.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'm', 'FLOW_AI_URL': 'https://x.test/v1/chat/completions',
                                           'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0'}); self.env.start()
        app.init(); self.c = app.db()
        for n in ('learner', 'other'):
            self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', (n, 'h'))
        self.c.commit()
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'daily', 'themes': [], 'minutes': 30})
        self.model = patch('chat_service.request_model', fake); self.model.start()
        fake.end = END

    def tearDown(self):
        self.model.stop(); self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def at(self, rid, t):
        self.assertEqual(self.c.execute('UPDATE lab_jobs SET created=? WHERE request_id=?', (t, rid)).rowcount, 1); self.c.commit()

    def say(self, rid, hist, text=None, end=False, t=None, uid=1, sid='cafe-order'):
        data = {'scenario': sid, 'history': hist, 'request_id': rid, **({'text': text} if text else {}), **({'end': True} if end else {})}
        r, code = out.dialog(self.c, uid, data)
        self.assertEqual(code, 200, r)
        if t is not None:
            self.at(rid, t)
        return r

    def cafe(self, uid=1, start=T0, tag='a'):
        """One scene dialog: the opening, two lines, the end."""
        hist = [{'role': 'ai', 'text': 'Hi! What can I get you?'}]
        self.say('hist-open-000' + tag, [], t=start if not self.c.execute('SELECT 1 FROM next_dialog_openers').fetchone() else None, uid=uid)
        self.say('hist-turn-001' + tag, hist, 'I want a latte, big one.', t=start + 60, uid=uid)
        hist += [{'role': 'me', 'text': 'I want a latte, big one.'}, {'role': 'ai', 'text': 'Sure. Anything else?'}]
        self.say('hist-turn-002' + tag, hist, 'For here please.', t=start + 120, uid=uid)
        hist += [{'role': 'me', 'text': 'For here please.'}, {'role': 'ai', 'text': 'Sure. Anything else?'}]
        self.say('hist-end-0000' + tag, hist, end=True, t=start + 200, uid=uid)

    def items(self, uid=1, **q):
        body, code = hs.listing(self.c, uid, {k: [str(v)] for k, v in q.items()})
        self.assertEqual(code, 200, body)
        return body

    def test_a_dialog_is_one_record_with_its_rounds_and_a_second_go_is_round_2(self):
        self.cafe()
        hist = [{'role': 'ai', 'text': 'Hi! What can I get you?'}]
        self.say('hist-turn-stray', hist, 'Hello there.', t=T0 + 3000)  # left without an end, well before the next go
        fake.end = {**END, 'fixes': [], 'expressions': []}
        self.say('hist-turn-003b', hist, 'A tea, please.', t=T0 + 5000)  # the opening is kept for everyone now: no row
        self.say('hist-end-0000b', hist + [{'role': 'me', 'text': 'A tea, please.'}, {'role': 'ai', 'text': 'Sure.'}], end=True, t=T0 + 5100)
        body = self.items()
        self.assertEqual((body['total'], body['more'], body['last']), (2, False, int(T0 + 5100)))
        new, old = body['items']
        self.assertEqual((new['kind'], new['type'], new['label'], new['title'], new['round']), ('dialog', 'speaking', '口语情景', '在咖啡店点单', 2))
        self.assertEqual((old['score'], old['note'], old['round']), ('78 分', '说了 2 句 · 改了 1 处', 1))
        self.assertEqual(new['note'], '说了 1 句 · 没有要改的')
        self.assertEqual(old['day'], time.strftime('%Y-%m-%d', time.gmtime(T0 + 200 + 8 * 3600)))
        d, code = hs.one(self.c, 1, old['id'])
        self.assertEqual(code, 200)
        self.assertEqual(d['said'], ['I want a latte, big one.', 'For here please.'])
        self.assertEqual((d['fixes'], d['saved'], d['minutes'], d['again'], d['lang']), ({'total': 1, 'kept': 1}, [], 4, '#/speak/cafe-order', 'zh'))
        self.assertEqual(d['result']['summary'], END['summary'])
        self.assertEqual(nx.save_card(self.c, 1, {'text': 'Is it for here or to go?', 'meaning': '在这儿喝还是带走？'})[1], 200)
        self.assertEqual(hs.one(self.c, 1, old['id'])[0]['saved'], ['Is it for here or to go?'])
        self.assertEqual(hs.one(self.c, 1, new['id'])[0]['said'], ['A tea, please.'])
        with patch('ui_lang.lang', return_value='en'):  # 全英文界面: the words the server writes come in English
            en = self.items()['items'][1]
        self.assertEqual((en['label'], en['title'], en['score'], en['note']), ('Speaking scene', 'Ordering at a café', '78/100', '2 lines · 1 fix'))

    def test_a_card_finds_the_record_it_came_from(self):
        self.cafe()
        item = self.items()['items'][0]
        self.assertEqual(hs.origin(self.c, 1, 'hist-end-0000a'), {'id': item['id'], 'label': '口语情景', 'title': '在咖啡店点单', 'at': item['at']})
        for uid, rid in ((2, 'hist-end-0000a'), (1, 'hist-turn-001a'), (1, ''), (1, None)):
            self.assertIsNone(hs.origin(self.c, uid, rid), (uid, rid))  # not yours, a round, none

    def test_an_old_card_without_a_request_id_finds_its_record_by_its_text(self):
        self.cafe(start=time.time() - 300)  # the card is made just after the end (now); the end row says when it was asked
        item = self.items()['items'][0]
        card = self.c.execute("SELECT * FROM next_cards WHERE source='mistake'").fetchone()
        self.assertNotIn('rid', json.loads(card['extra']))  # cards from before B2's extra.rid
        self.assertEqual(hs.source_of(self.c, 1, card), {'id': item['id'], 'label': '口语情景', 'title': '在咖啡店点单', 'at': item['at']})
        self.assertEqual(hs.source_of(self.c, 1, {**dict(card), 'extra': json.dumps({'rid': 'hist-end-0000a'})}), hs.origin(self.c, 1, 'hist-end-0000a'))
        self.assertIsNone(hs.source_of(self.c, 2, card))
        self.assertIsNone(hs.source_of(self.c, 1, {**dict(card), 'norm': 'fix:something else'}))
        self.assertIsNone(hs.source_of(self.c, 1, {**dict(card), 'created': card['created'] + 3600}))
        self.assertIsNone(hs.source_of(self.c, 1, {**dict(card), 'source': 'word'}))
        hs.delete(self.c, 1, {'id': item['id'], 'mistakes': False})
        self.assertIsNone(hs.source_of(self.c, 1, card))  # the record is gone; the card stays

    def test_only_your_own_records_and_ids_from_elsewhere_are_not_found(self):
        self.cafe()
        rid = self.items()['items'][0]['id']
        self.assertEqual(self.items(uid=2)['total'], 0)
        self.assertEqual(hs.one(self.c, 2, rid)[1], 404)
        self.assertEqual(hs.delete(self.c, 2, {'id': rid, 'mistakes': True})[1], 404)
        turn = self.c.execute("SELECT id FROM lab_jobs WHERE request_id='hist-turn-001a'").fetchone()['id']
        for bad in ('j%d' % turn, 'j999999', 'zzz', '', 'j1; DROP'):
            self.assertEqual(hs.one(self.c, 1, bad)[1], 404, bad)  # a round is not a record of its own
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM lab_jobs').fetchone()[0], 4)

    def test_delete_needs_the_mistakes_choice_and_takes_the_rounds_and_its_mistakes(self):
        self.cafe()
        rid = self.items()['items'][0]['id']
        self.assertEqual(nx.save_card(self.c, 1, {'text': 'Is it for here or to go?'})[1], 200)
        events = self.c.execute('SELECT COUNT(*) FROM next_skill_events').fetchone()[0]
        for data in ({'id': rid}, {'id': rid, 'mistakes': 'yes'}, {'id': rid, 'mistakes': 1}):
            self.assertEqual(hs.delete(self.c, 1, data)[1], 400, data)
        self.assertEqual(hs.delete(self.c, 1, {'id': rid, 'mistakes': True}), ({'ok': True, 'mistakes': 1}, 200))
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM lab_jobs').fetchone()[0], 0)  # the end, both lines and the opening
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_cards WHERE source='mistake'").fetchone()[0], 0)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_cards WHERE source!='mistake'").fetchone()[0], 1)  # 收藏 stays
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM next_skill_events').fetchone()[0], events)  # the scores stay
        self.assertEqual(hs.delete(self.c, 1, {'id': rid, 'mistakes': True})[1], 404)

    def test_keeping_the_mistakes_keeps_the_card(self):
        self.cafe()
        rid = self.items()['items'][0]['id']
        self.assertEqual(hs.delete(self.c, 1, {'id': rid, 'mistakes': False}), ({'ok': True, 'mistakes': 0}, 200))
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_cards WHERE source='mistake'").fetchone()[0], 1)

    def test_ielts_part1_is_its_feedback_with_the_answers_before_it(self):
        ie = __import__('ielts_speaking')
        for i, (rid, text) in enumerate((('hist-ie-ans-001', 'I am study law.'), ('hist-ie-ans-002', 'Yes, I like it a lot.'))):
            r, code = ie.post(self.c, 1, {'step': 'answer', 'topic': 'study-work', 'q': i, 'text': text, 'request_id': rid})
            self.assertEqual(code, 200, r); self.at(rid, T0 + 30 * i)
        r, code = ie.post(self.c, 1, {'step': 'part1', 'topic': 'study-work', 'request_id': 'hist-ie-feedback',
                                      'answers': [{'q': 0, 'text': 'I am study law.'}, {'q': 1, 'text': 'Yes, I like it a lot.'}]})
        self.assertEqual(code, 200, r); self.at('hist-ie-feedback', T0 + 90)
        item = self.items(type='speaking')['items'][0]
        self.assertEqual((item['kind'], item['label'], item['title'], item['score'], item['note']),
                         ('ielts', '雅思口语', 'Part 1 · 学习还是工作', '6.0', '答了 2 题 · 改了 1 处'))
        d = hs.one(self.c, 1, item['id'])[0]
        self.assertEqual((d['said'], d['again'], d['fixes']), (['I am study law.', 'Yes, I like it a lot.'], '#/speak/ielts/p1-study-work', {'total': 1, 'kept': 1}))
        self.assertEqual(hs.delete(self.c, 1, {'id': item['id'], 'mistakes': False})[0]['ok'], True)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM lab_jobs').fetchone()[0], 0)

    def test_retell_and_rewrite_read_back_as_the_page_showed_them(self):
        pid = nx.home(self.c, 1, 'B1')['today'][0]['id']
        r, code = out.retell(self.c, 1, {'pack': pid, 'text': 'The man goes home and he goed to sleep early that night.', 'request_id': 'hist-retell-0001'})
        self.assertEqual(code, 200, r)
        with patch('chat_service.request_model', return_value=(json.dumps(REWRITE), 'stop')):
            self.assertEqual(nx.rewrite(self.c, 1, {'pack': pid, 'text': 'If I left earlier I would catch the bus.', 'request_id': 'hist-rewrite-001'})[1], 200)
        self.assertEqual(nx.save_card(self.c, 1, {'text': 'make the bus'})[1], 200)
        rw, rt = self.items(type='writing')['items']
        self.assertEqual((rt['kind'], rt['label'], rt['score'], rt['note']), ('retell', '复述', '%d 分' % round(r['result']['score'] * 100), '讲到 1/2 个要点 · 改了 1 处'))
        self.assertEqual((rw['kind'], rw['label'], rw['score'], rw['note']), ('rewrite', '仿写', '小改', '改了 1 处'))
        self.assertEqual(hs.one(self.c, 1, rt['id'])[0]['result']['score'], r['result']['score'])
        d = hs.one(self.c, 1, rw['id'])[0]
        self.assertEqual((d['saved'], d['again'], d['said']), (['make the bus'], '#/m/%s/output' % pid, None))
        self.assertEqual(hs.one(self.c, 1, rt['id'])[0]['again'], '#/m/%s/output/retell' % pid)
        self.assertEqual(self.items(type='speaking')['total'], 0)  # a typed retelling is writing

    def test_tests_and_exams_are_listed_but_not_deleted_here(self):
        self.c.execute("INSERT INTO next_assess(user_id,skill,idx,level,detail,created) VALUES(1,'listening',0.5,'B1','{}',?)", (T0,))
        self.c.execute("INSERT INTO next_exam_results(user_id,exam,paper,score,total,parts,seconds,created) VALUES(1,'cet4','p1',8,10,'{}',600,?)", (T0 + 10,))
        self.c.execute("INSERT INTO next_exam_results(user_id,exam,paper,score,total,parts,seconds,created) VALUES(2,'cet4','p2',3,10,'{}',60,?)", (T0 + 20,))
        self.c.commit()
        self.cafe(start=T0 + 100)
        body = self.items()
        self.assertEqual([x['kind'] for x in body['items']], ['dialog', 'exam', 'assess'])
        ex, a = body['items'][1:]
        self.assertEqual((ex['title'], ex['score'], ex['note'], ex['open']), ('大学英语四级', '8/10', '用时 10 分钟', '#/exam/cet4'))
        self.assertEqual((a['title'], a['score'], a['label'], a['open']), ('听力', 'B1', '能力测评', '#/radar'))
        self.assertEqual(self.items(type='exam')['total'], 1)
        self.assertEqual(self.items(kind='assess', pack='listening')['total'], 1)
        self.assertEqual(self.items(type='speaking', kind='exam')['total'], 0)
        for rid in (ex['id'], a['id']):
            self.assertEqual(hs.delete(self.c, 1, {'id': rid, 'mistakes': False})[1], 400)
        self.assertEqual(hs.delete_all(self.c, 1, {'mistakes': True}), ({'ok': True, 'records': 1, 'mistakes': 1}, 200))
        self.assertEqual([x['kind'] for x in self.items()['items']], ['exam', 'assess'])

    def test_delete_all_takes_every_practice_row_and_leaves_the_other_learner(self):
        self.cafe()
        self.cafe(uid=2, tag='z')
        hist = [{'role': 'ai', 'text': 'Hi! What can I get you?'}]
        self.say('hist-turn-left1', hist, 'Just looking.', t=T0 + 9000)  # a dialog left before its end
        self.assertEqual(hs.delete_all(self.c, 1, {}), ({'error': '请选择错题要不要一起删', 'code': 'mistakes'}, 400))
        self.assertEqual(hs.delete_all(self.c, 1, {'mistakes': False}), ({'ok': True, 'records': 1, 'mistakes': 0}, 200))
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM lab_jobs WHERE user_id=1').fetchone()[0], 0)
        self.assertEqual(self.items(uid=2)['total'], 1)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_cards WHERE source='mistake' AND user_id=1").fetchone()[0], 1)

    def test_paging_goes_back_with_before(self):
        for i in range(5):
            rid = 'hist-essay-%04d' % i
            self.c.execute("INSERT INTO lab_jobs(user_id,request_id,kind,pack,skill,fingerprint,status,result,created,updated) VALUES(1,?,'next-essay','none','writing','f','complete',?,?,?)",
                           (rid, json.dumps({'scores': {'content': 4, 'organization': 4, 'accuracy': 3, 'range': 3}, 'level': None, 'comment': 'ok', 'fixes': []}), T0 + i, T0 + i))
        self.c.execute("INSERT INTO lab_jobs(user_id,request_id,kind,pack,skill,status,result,created) VALUES(1,'hist-essay-fail','next-essay','none','writing','failed','',?)", (T0 + 9,))
        self.c.commit()
        a = self.items(limit=2)
        self.assertEqual((len(a['items']), a['more'], a['total']), (2, True, 5))
        self.assertEqual(a['items'][0]['score'], '14/20')
        b = self.items(limit=2, before=a['items'][-1]['at'])
        c = self.items(limit=2, before=b['items'][-1]['at'])
        self.assertEqual((len(b['items']), b['more'], len(c['items']), c['more']), (2, True, 1, False))
        self.assertEqual(len({x['id'] for x in a['items'] + b['items'] + c['items']}), 5)
        self.assertEqual(self.items(limit=999)['total'], 5)
        for q in ({'type': 'video'}, {'kind': 'chat'}, {'pack': 'x'}, {'limit': 'ten'}, {'before': 'yesterday'}):
            self.assertEqual(hs.listing(self.c, 1, {k: [v] for k, v in q.items()})[1], 400, q)

    def test_the_mistake_cards_are_found_by_the_rule_that_made_them(self):
        fixes = [{'from': 'He go to School!', 'to': 'He goes to school!', 'why': ''}, {'from': '—', 'to': 'x', 'why': ''},
                 {'from': 'Same', 'to': 'same', 'why': ''}]
        sk.mistakes_from_changes(self.c, 1, fixes, 'He go to School!', 'writing', 'p', kind='essay')
        made = {r['id'] for r in self.c.execute("SELECT id FROM next_cards WHERE source='mistake'")}
        self.assertEqual(len(made), 1)
        self.assertEqual(set(hs._cards(self.c, 1, hs._norms({'fixes': fixes}))), made)
        self.assertEqual(hs._cards(self.c, 2, hs._norms({'fixes': fixes})), [])


class HistoryHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'h.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0'}); self.env.start()
        app.SECURE = False
        app.init()
        with app.db() as c:
            c.execute('INSERT INTO users(username,password,storage_ok,terms_version) VALUES(?,?,1,?)',
                      ('learner', app.password('correct horse battery'), __import__('privacy_service').CONSENT_VERSION))
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler); threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.cookie = ''

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def call(self, path, data=None, csrf=None):
        h = {'Content-Type': 'application/json', 'Cookie': self.cookie}
        if csrf: h['X-CSRF-Token'] = csrf
        req = urllib.request.Request(f'http://127.0.0.1:{self.srv.server_address[1]}{path}', data=json.dumps(data).encode() if data is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.headers.get('Set-Cookie'): self.cookie = r.headers['Set-Cookie'].split(';')[0]
                return r.status, json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')

    def test_signed_out_is_401_and_signed_in_reads_and_deletes_its_own(self):
        for path, data in (('/api/next/history', None), ('/api/next/history/j1', None),
                           ('/api/next/history/delete', {'id': 'j1', 'mistakes': True}), ('/api/next/history/delete-all', {'mistakes': True})):
            self.assertEqual(self.call(path, data)[0], 401, path)
        self.assertEqual(self.call('/api/login', {'username': 'learner', 'password': 'correct horse battery'})[0], 200)
        csrf = self.call('/api/session')[1]['user']['csrf']
        self.assertEqual(self.call('/api/next/history'), (200, {'items': [], 'more': False, 'total': 0, 'last': None}))
        self.assertEqual(self.call('/api/next/history?limit=1')[1]['total'], 0)
        self.assertEqual(self.call('/api/next/history/j1')[0], 404)
        self.assertEqual(self.call('/api/next/history/delete-all', {'mistakes': True})[0], 403)  # no CSRF token
        self.assertEqual(self.call('/api/next/history/delete', {'id': 'j1'}, csrf)[0], 400)
        self.assertEqual(self.call('/api/next/history/delete', {'id': 'a1', 'mistakes': False}, csrf)[0], 400)
        self.assertEqual(self.call('/api/next/history/delete-all', {'mistakes': True}, csrf), (200, {'ok': True, 'records': 0, 'mistakes': 0}))


if __name__ == '__main__':
    unittest.main()
