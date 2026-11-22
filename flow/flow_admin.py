"""Operator API for xmc.hk/flow/ (read-mostly).

Listens only on 127.0.0.1:FLOW_ADMIN_PORT. The sole route in is the xmc.hk
nginx location /flow/api/, which sits behind Cloudflare Access; flow.jasa.hk
never proxies here. Mutations additionally require the X-Requested-With: xmc
header, which a cross-site form or image cannot send.
"""
import json, os, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs

import survey_service as survey

PREFIX = '/flow/api'


def overview(c):
    import chat_service
    now = time.time()
    day = time.strftime('%Y-%m-%d', time.gmtime(now))
    week = [time.strftime('%Y-%m-%d', time.gmtime(now - i * 86400)) for i in range(7)]
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    return {
        'users': q('SELECT COUNT(*) FROM users'),
        'admins': q('SELECT COUNT(*) FROM users WHERE admin=1'),
        'active_7d': q('SELECT COUNT(DISTINCT user_id) FROM learning_events WHERE created>?', now - 7 * 86400),
        'active_1d': q('SELECT COUNT(DISTINCT user_id) FROM learning_events WHERE created>?', now - 86400),
        'events_7d': q('SELECT COUNT(*) FROM learning_events WHERE created>?', now - 7 * 86400),
        'ai': {
            'today': q('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE day=?', day),
            'week': [{'day': d, 'count': q('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE day=?', d)} for d in reversed(week)],
            'site_limit': chat_service.daily_limit('FLOW_AI_DAILY_LIMIT'),
            'user_limit': chat_service.daily_limit('FLOW_AI_USER_DAILY_LIMIT'),
            'users_at_limit': (q('SELECT COUNT(*) FROM ai_usage WHERE day=? AND user_id>0 AND count>=?', day, chat_service.daily_limit('FLOW_AI_USER_DAILY_LIMIT'))
                               if chat_service.daily_limit('FLOW_AI_USER_DAILY_LIMIT') else 0),
            'model': os.getenv('FLOW_AI_MODEL', ''),
        },
        'survey_responses': q('SELECT COUNT(*) FROM survey_responses WHERE survey=? AND hidden=0', survey.SURVEY_ID),
        'generated_at': now,
    }


class AdminHandler(BaseHTTPRequestHandler):
    server_version = 'FlowAdmin'

    def log_message(self, *args):
        pass

    def _send(self, obj, status=200, body=None, mime='application/json; charset=utf-8', extra=None):
        body = body if body is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self, method):
        import app
        url = urlsplit(self.path)
        path, qs = url.path, parse_qs(url.query)
        one = lambda k, d='': (qs.get(k) or [d])[0]
        if not path.startswith(PREFIX + '/'):
            return self._send({'error': '接口不存在'}, 404)
        path = path[len(PREFIX):]
        with app.db() as c:
            if method == 'GET':
                if path == '/overview':
                    return self._send(overview(c))
                if path == '/survey/definition':
                    return self._send(survey.SURVEY)
                if path == '/survey/summary':
                    filters = {k: one(k) for k in ('role', 'level', 'flow')}
                    return self._send(survey.summary(c, filters))
                if path == '/survey/responses':
                    return self._send(survey.responses(c, int(one('page', '1') or 1), 20, one('q')[:100]))
                if path == '/survey/export.csv':
                    name = f"flow-survey-{time.strftime('%Y%m%d')}.csv"
                    return self._send(None, body=survey.export_csv(c), mime='text/csv; charset=utf-8',
                                      extra={'Content-Disposition': f'attachment; filename="{name}"'})
            elif method == 'POST':
                if self.headers.get('X-Requested-With') != 'xmc':
                    return self._send({'error': '缺少请求标记'}, 403)
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 2000:
                    return self._send({'error': '请求大小不正确'}, 400)
                data = json.loads(self.rfile.read(length))
                if path == '/survey/hide':
                    return self._send(*survey.set_hidden(c, int(data['id']), bool(data.get('hidden', True))))
        return self._send({'error': '接口不存在'}, 404)

    def do_GET(self):
        try:
            self._route('GET')
        except (ValueError, KeyError, TypeError):
            self._send({'error': '参数不正确'}, 400)
        except Exception:
            self._send({'error': '服务暂时异常'}, 500)

    def do_POST(self):
        try:
            self._route('POST')
        except (ValueError, KeyError, TypeError):
            self._send({'error': '参数不正确'}, 400)
        except Exception:
            self._send({'error': '服务暂时异常'}, 500)


def start():
    """Start the operator API when FLOW_ADMIN_PORT is set. Always loopback-only."""
    port = int(os.getenv('FLOW_ADMIN_PORT', '0') or 0)
    if not port:
        return None
    server = ThreadingHTTPServer(('127.0.0.1', port), AdminHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name='flow-admin', daemon=True).start()
    print('Flow admin listening', server.server_address, flush=True)
    return server
