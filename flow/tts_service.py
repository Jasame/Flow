"""Server voice (r28): the sentences the site used to leave to the browser's own voice (AI replies, scene dialogues, the
IELTS examiner, examples without a recording, look-up sentences, 今日好句 quotes, grammar and exam examples) are spoken
by CosyVoice through the xmc-api gateway (POST <gateway>/v1/audio/speech, model FLOW_TTS_MODEL, the text AI's key).

The owner chose it after listening to samples (2026-11-24): it sounds standard and comfortable, and it works in
Android WeChat, which has no browser voice at all. Their idea shaped the storage: a sentence is made once per voice, on
the first tap anyone gives it (or overnight, prewarm()), kept under <audio>/tts/<voice>/<hash>.mp3, and everyone after
gets the stored file. The 语流 and 内测版 share the audio folder, so they share these files too. The voice follows
我的 → 朗读声音: us-f Abby, us-m Andy, uk-f Emily, uk-m Eric. Text narration stays Kokoro (owner: 「先不换」).

Off unless FLOW_TTS_MODEL is set. Guests get stored files only. A signed-in learner may make new ones within
FLOW_TTS_USER_CHARS characters a day, the site within FLOW_TTS_DAILY_CHARS; past either the page uses the browser voice.
Overnight prewarm has its own FLOW_TTS_PREWARM_CHARS. Characters are what the gateway bills (¥1 per 10,000, list price).

The folder must be writable by the Flow process. On 香港 both services run with systemd ProtectSystem=strict, so each
needs ReadWritePaths=<audio>/tts (a drop-in); without it every new sentence was paid for and then lost (内测版,
2026-11-24 23:40). Now the folder is checked before the gateway is called: not writable → StoreError, 503 code 'store'
(the page switches to the browser voice), one log line, no charge.
"""
import datetime, hashlib, json, os, re, tempfile, threading, time, urllib.error, urllib.request
from pathlib import Path

VOICES = {'us-f': 'loongabby_v3', 'us-m': 'loongandy_v3', 'uk-f': 'loongemily_v3', 'uk-m': 'loongeric_v3'}
MAX_CHARS = 1500
NAME = re.compile(r'[0-9a-f]{32}\.mp3')
LETTERS = re.compile(r'[A-Za-z]{2}')
_LOCKS, _GUARD = {}, threading.Lock()
_WARNED = set()


class StoreError(Exception):
    """The audio folder cannot be written (permissions, a read-only mount, a full disk)."""


def _warn(what, err):
    if what not in _WARNED:  # once per process: the log should say why, not repeat it for every tap
        _WARNED.add(what)
        print(f'tts: cannot write {what}: {err}', flush=True)


def writable(voice):
    """Whether the folder for this voice can take a new file; made if missing. False on a read-only mount too."""
    d = directory() / voice
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        _warn(d, e)
        return False
    if not os.access(d, os.W_OK):
        _warn(d, 'no write access (systemd ReadWritePaths?)')
        return False
    return True


def _int(name, default):
    try:
        return max(0, int(os.getenv(name, default)))
    except ValueError:
        return default


def model():
    return os.getenv('FLOW_TTS_MODEL', '').strip()


def enabled():
    return bool(model() and speech_url() and os.getenv('FLOW_AI_KEY'))


def speech_url():
    """FLOW_TTS_URL, else the text AI's gateway address with /chat/completions → /audio/speech."""
    u = os.getenv('FLOW_TTS_URL', '').strip() or os.getenv('FLOW_AI_URL', '').strip()
    if not u:
        return ''
    if u.endswith('/chat/completions'):
        return u[:-len('/chat/completions')] + '/audio/speech'
    return u if u.endswith('/audio/speech') else u.rstrip('/') + '/v1/audio/speech'


def norm(text):
    return ' '.join(str(text or '').split())


def name_of(text, voice):
    """The stored file's name. Everything that changes the sound is in the hash: the model (FLOW_TTS_MODEL), the
    upstream voice and the format, so a site on another model or a remapped voice never gets the old files (语流 2,
    2026-11-24). The gateway alias hides the upstream model: pointing flow-tts at another model means a new alias name
    (flow-tts-2) and FLOW_TTS_MODEL set to it, which starts a fresh set of files."""
    key = '\n'.join((model(), VOICES.get(voice, voice), 'mp3', norm(text)))
    return hashlib.sha256(key.encode()).hexdigest()[:32] + '.mp3'


def directory():
    import next_service as nx
    return Path(nx.AUDIO_DIR) / 'tts'


def file(voice, name):
    """The stored file for /audio/tts/<voice>/<name>, or None."""
    if voice not in VOICES or not NAME.fullmatch(name or ''):
        return None
    f = directory() / voice / name
    return f if f.is_file() else None


def url(voice, name):
    return f'/audio/tts/{voice}/{name}'


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS tts_usage(day TEXT NOT NULL, who INTEGER NOT NULL, chars INTEGER NOT NULL DEFAULT 0, '
              'files INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(day, who))')  # who: a learner's id, 0 = the site, -1 = overnight


def _day():
    import next_service as nx
    return datetime.datetime.now(nx.TZ).date().isoformat()


def _used(c, who, day=None):
    r = c.execute('SELECT chars FROM tts_usage WHERE day=? AND who=?', (day or _day(), who)).fetchone()
    return r[0] if r else 0


def _add(c, who, chars, files, day=None):
    c.execute('INSERT INTO tts_usage(day, who, chars, files) VALUES(?,?,?,?) ON CONFLICT(day, who) DO UPDATE SET '
              'chars=chars+excluded.chars, files=files+excluded.files', (day or _day(), who, chars, files))


def _lock(name):
    with _GUARD:
        return _LOCKS.setdefault(name, threading.Lock())


def _speak(text, voice):
    """mp3 bytes for one sentence from the gateway; raises on any failure."""
    body = json.dumps({'model': model(), 'input': text, 'voice': VOICES[voice], 'response_format': 'mp3'}).encode()
    req = urllib.request.Request(speech_url(), data=body, method='POST', headers={
        'Authorization': 'Bearer ' + os.getenv('FLOW_AI_KEY', ''), 'Content-Type': 'application/json', 'User-Agent': 'flow-tts/1.0'})
    with urllib.request.urlopen(req, timeout=int(os.getenv('FLOW_TTS_TIMEOUT', '30'))) as r:
        data = r.read(8_000_001)
    if not 100 < len(data) <= 8_000_000 or not (data[:3] == b'ID3' or data[0] == 0xFF):
        raise ValueError('not an mp3')
    return data


def _store(f, data):
    f.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=f.parent, prefix='.' + f.name + '.')
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, f)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def ensure(c, who, text, voice, cap=None):
    """(url, made) for this sentence in this voice; makes it when it is not stored yet and `who` may.
    who: a learner's id, None for a guest (stored files only), -1 for overnight prewarm (cap = that night's budget left).
    Raises LookupError (guest, nothing stored), PermissionError (a cap reached), ValueError (bad text), OSError (gateway),
    StoreError (the folder cannot be written: checked before the gateway is paid)."""
    text = norm(text)
    if voice not in VOICES:
        voice = 'us-f'
    if not text or len(text) > MAX_CHARS or not LETTERS.search(text):
        raise ValueError('text')
    name = name_of(text, voice)
    if file(voice, name):
        return url(voice, name), False
    if who is None:
        raise LookupError('not stored')
    n = len(text)
    if who != -1 and (_used(c, who) + n > _int('FLOW_TTS_USER_CHARS', 20000) or _used(c, 0) + n > _int('FLOW_TTS_DAILY_CHARS', 200000)):
        raise PermissionError('cap')
    if who == -1 and cap is not None and n > cap:
        raise PermissionError('cap')
    if not writable(voice):
        raise StoreError('folder')
    with _lock(voice + name):
        if file(voice, name):  # made by another request while this one waited
            return url(voice, name), False
        try:
            data = _speak(text, voice)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise OSError(str(e)[:120])
        try:
            _store(directory() / voice / name, data)
        except OSError as e:
            _warn(directory() / voice, e)
            raise StoreError('store')
    _add(c, who, n, 1)
    if who != -1:
        _add(c, 0, n, 1)
    c.commit()
    return url(voice, name), True


def post(c, uid, data):
    """POST /api/next/tts {text, voice}: the stored file's address, made now if need be. Open to guests (stored only)."""
    if not enabled():
        return {'error': '服务器朗读没有开启', 'code': 'off'}, 503
    try:
        u, made = ensure(c, uid, data.get('text'), data.get('voice') if data.get('voice') in VOICES else 'us-f')
    except ValueError:
        return {'error': '这段文字不能朗读'}, 400
    except LookupError:
        return {'error': '登录后可以用 AI 朗读', 'code': 'guest'}, 404
    except PermissionError:
        return {'error': '今天的 AI 朗读用完了，先用浏览器的声音', 'code': 'cap'}, 429
    except StoreError:
        return {'error': 'AI 朗读暂时不能用，先用浏览器的声音', 'code': 'store'}, 503
    except OSError:
        return {'error': 'AI 朗读暂时没有生成出来', 'code': 'gateway'}, 502
    return {'url': u, 'made': made}, 200


# ---------- overnight ----------
# The server is idle at night (owner's idea): between 03:00 and 05:00 China time the Flow process starts prewarm() once
# in a thread of its own (app.remind_loop calls tick() every 5 minutes). 语流 and the 内测版 share the files, so a lock
# file lets one of them do it; the other then finds them stored.
_NIGHT = {'day': None}


def tick(db, now=None):
    import next_service as nx
    if not enabled():
        return
    t = datetime.datetime.fromtimestamp(now or time.time(), nx.TZ)
    if not 3 <= t.hour < 5 or _NIGHT['day'] == t.date().isoformat():
        return
    _NIGHT['day'] = t.date().isoformat()
    threading.Thread(target=_night, args=(db,), daemon=True).start()


def _night(db):
    import fcntl
    d = directory()
    try:
        d.mkdir(parents=True, exist_ok=True)
        lock = open(d / '.prewarm.lock', 'w')
    except OSError as e:
        _warn(d, e)
        print('tts prewarm:', json.dumps({'status': 'store'}), flush=True)
        return
    with lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return
        with db() as c:
            print('tts prewarm:', json.dumps(prewarm(c)), flush=True)


def fixed_texts():
    """Sentences the same for everyone, so worth making before anyone taps: the IELTS Part 1 questions, the scenes'
    useful expressions, the public-domain 今日好句."""
    import ielts_speaking as ie, scenarios as sc, daily_line as dl
    out = [q for _, _, qs in ie.PART1.values() for q in qs]
    out += [u[0] for s in sc.SCENES.values() for u in s[8] if '…' not in u[0]]
    out += [q[1].replace(' / ', ', ') for q in dl.QUOTES]
    return list(dict.fromkeys(norm(t) for t in out if t))


def voices_in_use(c, days=30):
    """The 朗读声音 of learners active lately (always us-f, the default)."""
    since = time.time() - days * 86400
    rows = c.execute("SELECT DISTINCT p.voice FROM next_profiles p WHERE p.user_id IN (SELECT user_id FROM next_progress WHERE created>?)", (since,)).fetchall()
    return list(dict.fromkeys(['us-f'] + [r[0] for r in rows if r[0] in VOICES]))


def prewarm(c, budget=None):
    """Make the fixed sentences in the voices learners use, within tonight's budget. Run by flow-daily (daily_service)."""
    if not enabled():
        return {'status': 'off'}
    budget = _int('FLOW_TTS_PREWARM_CHARS', 20000) if budget is None else budget
    left = budget - _used(c, -1)
    made = stored = failed = 0
    for voice in voices_in_use(c):
        for t in fixed_texts():
            if file(voice, name_of(t, voice)):
                stored += 1
                continue
            if len(t) > left:
                return {'status': 'budget', 'made': made, 'stored': stored, 'failed': failed}
            try:
                ensure(c, -1, t, voice, cap=left)
                made += 1
                left -= len(t)
            except StoreError:
                return {'status': 'store', 'made': made, 'stored': stored, 'failed': failed}
            except (OSError, PermissionError, ValueError):
                failed += 1
                if failed >= 5:
                    return {'status': 'gateway', 'made': made, 'stored': stored, 'failed': failed}
    return {'status': 'done', 'made': made, 'stored': stored, 'failed': failed}
