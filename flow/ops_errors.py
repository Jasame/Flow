"""Server errors that reached a learner as "服务暂时异常": logged with their stack trace and kept for the operator.

Each one goes to the service journal (journalctl -u flow) and to the server_errors table (the last 500), grouped by
where in the code it happened. Only the method and path are kept, never the query string or the request body, so no
learner input is stored. The operator page shows them (flow_admin /errors); /api/deploy-status shows the 24 h count.
"""
import hashlib
import sys
import time
import traceback

KEEP = 500


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS server_errors(id INTEGER PRIMARY KEY, created REAL NOT NULL, method TEXT NOT NULL, '
              'path TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL, trace TEXT NOT NULL, sig TEXT NOT NULL)')
    c.execute('CREATE INDEX IF NOT EXISTS server_errors_time ON server_errors(created)')


def signature(exc):
    """The same bug from the same place gets the same signature, whatever the request was."""
    frames = traceback.extract_tb(exc.__traceback__)[-3:]
    where = '|'.join(f'{f.filename.rsplit("/", 1)[-1]}:{f.name}:{f.lineno}' for f in frames)
    return hashlib.sha256(f'{type(exc).__name__}|{where}'.encode()).hexdigest()[:16]


def record(db, method, path, exc):
    """Called from the request handlers' last-resort except. Never raises."""
    try:
        trace = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-6000:]
        path = (path or '').split('?', 1)[0][:200]
        print(f'ERROR {method} {path}: {type(exc).__name__}: {exc}\n{trace}', file=sys.stderr, flush=True)
        with db() as c:
            schema(c)
            c.execute('INSERT INTO server_errors(created,method,path,kind,message,trace,sig) VALUES(?,?,?,?,?,?,?)',
                      (time.time(), method, path, type(exc).__name__, str(exc)[:500], trace, signature(exc)))
            c.execute('DELETE FROM server_errors WHERE id <= (SELECT MAX(id) FROM server_errors) - ?', (KEEP,))
    except Exception:
        pass


def count_since(c, seconds):
    try:
        return c.execute('SELECT COUNT(*) FROM server_errors WHERE created>?', (time.time() - seconds,)).fetchone()[0]
    except Exception:
        return 0


def recent(c, days=7):
    """Grouped by signature, newest first: how often, when last, on which paths, and the latest trace."""
    schema(c)
    since = time.time() - days * 86400
    groups = []
    for r in c.execute('SELECT sig, COUNT(*) n, MIN(created) first, MAX(created) last FROM server_errors WHERE created>? '
                       'GROUP BY sig ORDER BY last DESC LIMIT 50', (since,)).fetchall():
        last = c.execute('SELECT method, path, kind, message, trace FROM server_errors WHERE sig=? ORDER BY id DESC LIMIT 1', (r['sig'],)).fetchone()
        paths = [p for (p,) in c.execute('SELECT DISTINCT method || " " || path FROM server_errors WHERE sig=? AND created>? LIMIT 5', (r['sig'], since))]
        groups.append({'sig': r['sig'], 'count': r['n'], 'first': r['first'], 'last': r['last'], 'kind': last['kind'],
                       'message': last['message'], 'paths': paths, 'trace': last['trace']})
    return {'days': days, 'total': sum(g['count'] for g in groups), 'last_24h': count_since(c, 86400), 'groups': groups}
