"""今日热点's news search on 百炼 (FLOW_SEARCH_AI_MODEL): the search goes to the gateway's /v1/search/completions first and
to Gemini's own search when that fails; 百炼's [ref_N] citations become the pack's sources and supports, the brief loses
the marks, and the pack says who searched and who rewrote. Without the setting nothing changes."""
import copy, io, json, os, sys, tempfile, unittest, urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, ai_routes, chat_service as cs, daily_service as daily, lab_service as lab  # noqa: E402
from content_v07 import all_materials  # noqa: E402

GATEWAY = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_URL': 'https://gw.test/v1/chat/completions', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'gemini-3.8-flash',
           'FLOW_TEXT_AI_MODEL': 'flow-text', 'FLOW_AI_GROUNDING': '1', 'FLOW_AI_DAILY_LIMIT': '100'}
TEXT = ('On 24 November the city opened 12 km of new bike lanes [ref_1]. Officials said the lanes link two parks.[ref_2] '
        'Riders were pleased [ref_1][ref_3]. Some drivers complained about parking.')
RESULTS = [{'index': 1, 'url': 'https://news.example.com/bikes', 'title': 'City opens bike lanes', 'site_name': 'Example News'},
           {'index': 2, 'url': 'https://city.example.gov/notice', 'title': 'Notice', 'site_name': ''},
           {'index': 3, 'url': 'http://old.example.org/riders', 'title': 'Plain http'},
           {'index': 4, 'url': 'https://never.example.com/', 'title': 'Never cited'}]
META = {'engine': 'bailian', 'search_results': RESULTS, 'searches': 1}


class Reply:
    def __init__(self, body):
        self.body = json.dumps(body).encode()
        self.headers = {'Content-Type': 'application/json'}

    def __enter__(self):
        return io.BytesIO(self.body)

    def __exit__(self, *a):
        return False


def search_answer(text=TEXT, results=RESULTS):
    return {'model': 'deepseek-v4.1-flash-1017', 'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 1200, 'completion_tokens': 180, 'total_tokens': 1380},
            'search_info': {'search_results': results}, 'search_usage': {'count': 1, 'strategy': 'turbo'}}


class ProvenanceTests(unittest.TestCase):
    def test_cited_https_results_become_sources_and_sentences_supports(self):
        p = daily.provenance(TEXT, META)
        self.assertEqual(p['engine'], 'bailian')
        self.assertEqual([s['url'] for s in p['sources']], ['https://news.example.com/bikes', 'https://city.example.gov/notice'])
        self.assertEqual(p['sources'][0]['site'], 'Example News')
        self.assertNotIn('[ref_', p['brief'])
        self.assertTrue(p['brief'].startswith('On 24 November the city opened 12 km of new bike lanes. Officials said'))
        quotes = {s['quote']: s['sources'] for s in p['supports']}
        self.assertEqual(quotes, {'On 24 November the city opened 12 km of new bike lanes.': [0], 'Officials said the lanes link two parks.': [1],
                                  'Riders were pleased.': [0]})
        self.assertTrue(all(q in p['brief'] for q in quotes))
        self.assertEqual(p['suggestions'], '')

    def test_no_cited_or_only_plain_http_sources_is_refused(self):
        with self.assertRaises(ValueError):
            daily.provenance('Nothing is cited here.', META)
        with self.assertRaises(ValueError):
            daily.provenance('Riders were pleased [ref_3].', META)
        with self.assertRaises(ValueError):
            daily.provenance(TEXT, {'engine': 'bailian', 'search_results': []})
        with self.assertRaises(ValueError):
            daily.provenance('A mark to nowhere [ref_9].', META)

    def test_gemini_grounding_still_reads_as_before(self):
        meta = {'groundingChunks': [{'web': {'uri': 'https://example.org/news', 'title': 'Museum'}}],
                'groundingSupports': [{'segment': {'text': 'A museum opened.'}, 'groundingChunkIndices': [0]}],
                'searchEntryPoint': {'renderedContent': '<a href="https://google.com">x</a>'}}
        p = daily.provenance('A museum opened. More later.', meta)
        self.assertNotIn('engine', p)
        self.assertEqual(p['brief'], 'A museum opened. More later.')


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'search.db')
        self.p.start()
        app.init()
        self.env = patch.dict(os.environ, GATEWAY)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.p.stop()
        self.tmp.cleanup()

    def ask(self, script, env=None):
        sent = []

        def urlopen(req, timeout=None):
            sent.append((req.full_url, json.loads(req.data)))
            outcome = script.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return Reply(outcome)
        with patch.dict(os.environ, env or {}), patch('urllib.request.urlopen', urlopen), ai_routes.task('daily-search'):
            out = cs.request_model([{'role': 'system', 'content': 'News researcher.'}, {'role': 'user', 'content': 'One story.'}], grounding=True)
        return out, sent

    def calls(self):
        c = app.db()
        try:
            return [dict(r) for r in c.execute('SELECT kind,route,service,model,served,ok,fallback,prompt,completion FROM ai_calls ORDER BY id')]
        finally:
            c.close()

    def test_without_the_setting_gemini_searches_as_before(self):
        gem = {'model': 'gemini-3.8-flash', 'choices': [{'message': {'content': 'x'}, 'finish_reason': 'stop'}], 'flow_grounding': {'groundingChunks': []}}
        (reply, reason, meta), sent = self.ask([gem])
        self.assertEqual(sent[0][0], 'https://gw.test/v1/chat/completions')
        self.assertTrue(sent[0][1]['flow_grounding'])
        self.assertEqual(meta, {'groundingChunks': []})

    def test_bailian_search_first_through_the_gateways_search_route(self):
        (reply, reason, meta), sent = self.ask([search_answer()], {'FLOW_SEARCH_AI_MODEL': 'flow-search-ds-flash'})
        url, body = sent[0]
        self.assertEqual(url, 'https://gw.test/v1/search/completions')
        self.assertEqual(body['model'], 'flow-search-ds-flash')
        self.assertEqual(body['search'], {'strategy': 'turbo', 'freshness': 7})
        self.assertNotIn('flow_grounding', body)
        self.assertEqual((reply, reason), (TEXT, 'stop'))
        self.assertEqual(meta['engine'], 'bailian')
        self.assertEqual(meta['search_results'], RESULTS)
        row = self.calls()[-1]
        self.assertEqual((row['kind'], row['service'], row['model'], row['route'], row['served'], row['ok'], row['prompt'], row['completion']),
                         ('daily-search', 'search', 'flow-search-ds-flash', 'flow-search-ds-flash', 'deepseek-v4.1-flash-1017', 1, 1200, 180))

    def test_a_failing_bailian_search_hands_over_to_gemini(self):
        gem = {'model': 'gemini-3.8-flash', 'choices': [{'message': {'content': 'g'}, 'finish_reason': 'stop'}], 'flow_grounding': {'groundingChunks': [1]}}
        for failure in (urllib.error.HTTPError('https://gw.test', 400, 'bad', None, None), urllib.error.HTTPError('https://gw.test', 502, 'down', None, None), TimeoutError('slow')):
            (reply, reason, meta), sent = self.ask([failure, gem], {'FLOW_SEARCH_AI_MODEL': 'flow-search-ds-flash'})
            self.assertEqual([u for u, _ in sent], ['https://gw.test/v1/search/completions', 'https://gw.test/v1/chat/completions'])
            self.assertEqual(meta, {'groundingChunks': [1]})
            rows = self.calls()[-2:]
            self.assertEqual([(r['service'], r['ok'], r['fallback']) for r in rows], [('search', 0, 0), ('main', 1, 1)])

    def test_strategy_setting_and_text_tasks_untouched(self):
        _, sent = self.ask([search_answer()], {'FLOW_SEARCH_AI_MODEL': 'flow-search-ds-flash', 'FLOW_SEARCH_STRATEGY': 'max'})
        self.assertEqual(sent[0][1]['search']['strategy'], 'max')
        _, sent = self.ask([search_answer()], {'FLOW_SEARCH_AI_MODEL': 'flow-search-ds-flash', 'FLOW_SEARCH_STRATEGY': 'agent'})
        self.assertEqual(sent[0][1]['search']['strategy'], 'turbo')
        text = {'model': 'gemini-3.8-flash', 'choices': [{'message': {'content': 'plain'}, 'finish_reason': 'stop'}]}
        seen = []

        def urlopen(req, timeout=None):
            seen.append(req.full_url)
            return Reply(text)
        with patch.dict(os.environ, {'FLOW_SEARCH_AI_MODEL': 'flow-search-ds-flash'}), patch('urllib.request.urlopen', urlopen), ai_routes.task('chat'):
            cs.request_model([{'role': 'user', 'content': 'hi'}])
        self.assertEqual(seen, ['https://gw.test/v1/chat/completions'])


# DailyRunTests (the news search and rewrite of 今日热点) went with 今日热点 on 2026-11-25: 今日一读 searches nothing
# (tests/test_daily_knowledge.py). provenance() above stays for search_eval.py.


class SearchEvalHelperTests(unittest.TestCase):
    def test_dates_names_numbers_and_publish_dates(self):
        import datetime, search_eval as se
        today = datetime.date(2026, 11, 25)
        got = se.dates_in('On 24 November, and on Nov. 23 2026; also 2026-11-20 and December 30.', today)
        self.assertEqual([d.isoformat() for d in got], ['2025-12-30', '2026-11-20', '2026-11-23', '2026-11-24'])
        nums, names = se.facts('The city opened 12 km of lanes, costing 1,200,000 yuan, up 3.5%. Mayor Lina Park said Monday it helps.')
        self.assertEqual(nums, ['12', '1200000', '3.5%'])
        self.assertIn('Lina', names)
        self.assertNotIn('Monday', names)
        self.assertTrue(se.found_in('3.5%', ['prices rose 3.5 percent']))
        self.assertEqual(se.published('<meta property="article:published_time" content="2026-11-24T08:00:00Z">'), '2026-11-24')
        self.assertEqual(se.published('<script type="application/ld+json">{"datePublished": "2026-11-23"}</script>'), '2026-11-23')

    def test_private_addresses_are_never_opened(self):
        import search_eval as se
        for url in ('http://127.0.0.1:9000/v1/models', 'http://localhost/', 'http://10.0.0.5/', 'file:///etc/passwd', 'ftp://example.com/'):
            out = se.fetch(url)
            self.assertFalse(out['open'], url)
            self.assertIn('error', out)


if __name__ == '__main__':
    unittest.main()
