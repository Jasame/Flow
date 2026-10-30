import io,json,os,sys,unittest,urllib.error
from email.message import Message
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ai_stream,chat_service

class Reply(io.BytesIO):
    def __init__(self,body):
        super().__init__(body);self.headers=Message();self.headers['Content-Type']='text/event-stream'

def frame(text='',finish=None):
    return 'data: '+json.dumps({'choices':[{'delta':{'content':text},'finish_reason':finish}]},ensure_ascii=False)+'\n\n'

class StreamingTests(unittest.TestCase):
    def model(self,body):
        self.env=patch.dict(os.environ,{'FLOW_AI_PROVIDER':'openai','FLOW_AI_KEY':'private-test-key','FLOW_AI_URL':'https://gateway.test/v1/chat/completions','FLOW_AI_MODEL':'test-model'})
        self.env.start();self.addCleanup(self.env.stop)
        mocked=patch.object(chat_service.urllib.request,'urlopen',return_value=Reply(body.encode()))
        self.addCleanup(mocked.stop);return mocked.start()
    def test_parser_multiline_comments_crlf_and_unicode(self):
        self.assertEqual(list(ai_stream.events(io.BytesIO(': ping\r\ndata: {"x":\r\ndata: "你好"}\r\n\r\n'.encode()))),['{"x":\n"你好"}'])
    def test_visible_preview_does_not_leak_nested_memories_or_answers(self):
        raw='{"memory_updates":[{"reply":"PRIVATE"}],"reply":"你好\\nTry \\"this\\"", "missions":[{"reply":"SECRET"}]}'
        # Test escaped quotes independently and nested fields against well-formed JSON.
        raw=json.dumps({'memory_updates':[{'reply':'PRIVATE'}],'reply':'你好\nTry "this"','missions':[{'reply':'SECRET'}]},ensure_ascii=False)
        visible=ai_stream.preview(raw);self.assertEqual(visible,'你好\nTry "this"');self.assertNotIn('PRIVATE',visible)
        self.assertNotIn('answer',ai_stream.preview('{"questions":[{"answer":0}],"revision":"answer"}'))
    def test_partial_json_strings_and_unicode_escapes(self):
        self.assertEqual(ai_stream.preview('{"reply":"Try \\u4f60'), 'Try 你')
        self.assertEqual(ai_stream.preview('{"reply":"Try \\u4f'), 'Try ')
        self.assertEqual(ai_stream.preview('{"reply":"Try \\'), 'Try ')
    def test_model_stream_emits_actual_deltas_and_aggregates(self):
        mocked=self.model(frame('Hello ')+frame('世界','stop')+'data: [DONE]\n\n');seen=[]
        with ai_stream.observe(seen.append,structured=False):reply,reason=chat_service.request_model([{'role':'user','content':'Hi'}])
        self.assertEqual(reply,'Hello 世界');self.assertEqual(reason,'stop');self.assertEqual([e['text'] for e in seen],['Hello ','Hello 世界'])
        self.assertTrue(json.loads(mocked.call_args[0][0].data)['stream'])
    def test_truncation_filter_missing_finish_and_empty_rejected(self):
        for body in [frame('x'),frame('', 'stop'),frame('x','length'),frame('x','content_filter')]:
            with self.subTest(body=body):
                with patch.dict(os.environ,{'FLOW_AI_PROVIDER':'openai','FLOW_AI_KEY':'k','FLOW_AI_URL':'https://test.invalid','FLOW_AI_MODEL':'m'}),patch.object(chat_service.urllib.request,'urlopen',return_value=Reply(body.encode())),ai_stream.observe(lambda e:None):
                    with self.assertRaises(ValueError):chat_service.request_model([{'role':'user','content':'Hi'}])
    def test_stream_upstream_status_preserved(self):
        self.model('data: {"error":"failed","status":429}\n\n')
        with ai_stream.observe(lambda e:None):
            with self.assertRaises(urllib.error.HTTPError) as error:chat_service.request_model([{'role':'user','content':'Hi'}])
        self.assertEqual(error.exception.code,429)
    def test_json_gateway_not_silently_treated_as_stream(self):
        mocked=self.model('{}');mocked.return_value.headers.replace_header('Content-Type','application/json')
        with ai_stream.observe(lambda e:None):
            with self.assertRaises(ValueError):chat_service.request_model([{'role':'user','content':'Hi'}])
    def test_bounded_frames_and_thread_local_cleanup(self):
        with self.assertRaises(ValueError):list(ai_stream.events(io.BytesIO(b'data: '+b'x'*262145)))
        with ai_stream.observe(lambda e:None):self.assertTrue(ai_stream.active())
        self.assertFalse(ai_stream.active())
if __name__=='__main__':unittest.main()
