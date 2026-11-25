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
import sys
import aigc_label
import datetime, hashlib, json, os, re, shutil, tempfile, threading, time, urllib.error, urllib.request
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


def sample_rate():
    """FLOW_TTS_SAMPLE_RATE: 16000 or 22050 make smaller mp3s than the gateway's 24000 (语流 12, 2026-11-25); unset, the
    gateway's own. Part of each file's name, so a change makes a fresh set."""
    v = _int('FLOW_TTS_SAMPLE_RATE', 0)
    return v if v in (16000, 22050, 24000) else 0


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
    rate = sample_rate()
    key = '\n'.join((model(), VOICES.get(voice, voice), 'mp3' + (f'@{rate}' if rate else ''), norm(text)))
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


# ---------- a learner's own articles (imports): their sentences' voice is theirs only ----------
# Kept in the data folder (which the service may write; ops.backup skips it: all of it can be made again), one folder
# per learner, served at /audio/own/<voice>/<name> to that learner's session only (app.send_audio), never listed.
def own_dir(uid):
    return Path(__import__('console_ops').data_dir()) / 'tts-own' / str(int(uid))


def own_file(uid, voice, name):
    if not uid or voice not in VOICES or not NAME.fullmatch(name or ''):
        return None
    f = own_dir(uid) / voice / name
    return f if f.is_file() else None


def own_url(voice, name):
    return f'/audio/own/{voice}/{name}'


def _own_writable(folder):
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        _warn(folder, e)
        return False
    return os.access(folder, os.W_OK)


def _used_import(c, who, day=None):
    r = c.execute('SELECT chars FROM tts_import WHERE day=? AND who=?', (day or _day(), who)).fetchone()
    return r[0] if r else 0


def _own_pack(c, uid, pack):
    """An article that belongs to a learner: its text when it is this learner's, False when it is someone else's (or a guest
    asks), None when the material is shared (or not given)."""
    if not isinstance(pack, str) or not pack:
        return None
    row = c.execute('SELECT owner, content FROM lab_packs WHERE id=?', (pack,)).fetchone()
    if not row or row[0] is None:
        return None
    if not uid or row[0] != uid:
        return False
    try:
        return str(json.loads(row[1]).get('body') or '')
    except ValueError:
        return ''


def have(c, uid, data):
    """POST /api/next/tts/have {pack?, voice, texts}: which sentences are made already (their addresses, else null), nothing
    made: the page says 「正在准备朗读 12/30 句」 and knows what to ask for."""
    if not enabled():
        return {'error': '服务器朗读没有开启', 'code': 'off'}, 503
    texts = data.get('texts')
    if not isinstance(texts, list) or len(texts) > 400:
        return {'error': '句子太多了'}, 400
    voice = data.get('voice') if data.get('voice') in VOICES else 'us-f'
    own = _own_pack(c, uid, data.get('pack'))
    if own is False:
        return {'error': '文章不存在'}, 404
    out = []
    for t in texts:
        name = name_of(t, voice) if isinstance(t, str) else ''
        hit = (own_file(uid, voice, name) if own is not None else file(voice, name)) if name else None
        out.append((own_url if own is not None else url)(voice, name) if hit else None)
    return {'urls': out}, 200


_BATCH = threading.BoundedSemaphore(2)  # imports being made in the background at once (low priority; the page asks too)


def start_pack(uid, pack, voice=None, wait=False, pause=0.2, tries=3):
    """After an import: its sentences made one by one in a thread, slowly, a sentence that fails tried again a couple of
    times; stops at the learner's import share or the site's (the page then says why). Returns the thread or None."""
    if not enabled() or not CONNECT or not uid:
        return None
    if not _BATCH.acquire(blocking=False):
        return None

    def run():
        try:
            c = CONNECT()
            try:
                import next_service as nx
                body = _own_pack(c, uid, pack)
                if not body:
                    return
                v = voice if voice in VOICES else ((nx.profile(c, uid) or {}).get('voice') or 'us-f')
                for s in nx.sentences(body):
                    for k in range(tries):
                        try:
                            ensure(c, uid, s, v, own=True)
                            break
                        except PermissionError:
                            return  # a share is used up: the page says so when the article is opened
                        except (ValueError, LookupError, StoreError):
                            break
                        except OSError:
                            time.sleep(pause * 10 * (k + 1))
                    time.sleep(pause)
            finally:
                c.close()
        except Exception:  # noqa: BLE001  (the page asks for what is missing)
            pass
        finally:
            _BATCH.release()
    t = threading.Thread(target=run, daemon=True)
    t.start()
    if wait:
        t.join()
    return t


def forget(uid):
    """注销账号: the learner's own voice files go with the account."""
    if uid:
        shutil.rmtree(own_dir(uid), ignore_errors=True)


def forget_pack(uid, body):
    """An import deleted: its sentences' voice files go too (in every voice)."""
    import next_service as nx
    for s in nx.sentences(body or ''):
        for v in VOICES:
            f = own_file(uid, v, name_of(s, v))
            if f:
                try:
                    f.unlink()
                except OSError:
                    pass


def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS tts_usage(day TEXT NOT NULL, who INTEGER NOT NULL, chars INTEGER NOT NULL DEFAULT 0, '
              'files INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(day, who))')  # who: a learner's id, 0 = the site, -1 = overnight
    c.execute('CREATE TABLE IF NOT EXISTS tts_import(day TEXT NOT NULL, who INTEGER NOT NULL, chars INTEGER NOT NULL DEFAULT 0, '
              'PRIMARY KEY(day, who))')  # a learner's own articles (imports), on top of tts_usage: their own daily share


# ---------- caps (the console can change them: console-settings.json, like the AI call limits) ----------
# Which cap each kind of use counts against (语流 1 / 语流 2, 2026-11-25):
#   a tap or an AI reply (shared files):  the learner's FLOW_TTS_USER_CHARS and the site's FLOW_TTS_DAILY_CHARS
#   a learner's own article (imports):    the same two, plus FLOW_TTS_IMPORT_CHARS a learner a day, and only while the site
#                                         has used under FLOW_TTS_IMPORT_PERCENT of its day: replies and speaking keep the rest
#   overnight and the day's 热点:          FLOW_TTS_PREWARM_CHARS a day (who -1), not the site's share; skipped once the
#                                         console's daily AI budget is spent
CAPS = {'FLOW_TTS_USER_CHARS': 20000, 'FLOW_TTS_DAILY_CHARS': 200000, 'FLOW_TTS_IMPORT_CHARS': 10000, 'FLOW_TTS_IMPORT_PERCENT': 60,
        'FLOW_TTS_PREWARM_CHARS': 20000}


def cap(name):
    """A cap in force: the console's value, else the server's (/etc/flow.env), else the default above."""
    try:
        v = __import__('console_ops').limit_override(name)
    except Exception:  # noqa: BLE001
        v = None
    return v if v is not None else _int(name, CAPS[name])


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
    """mp3 bytes for one sentence from the gateway; raises on any failure. Each call is a row in ai_calls (kind 'tts',
    characters as the prompt), so the console's costs and daily budget include the voice (语流 12, #82)."""
    import ai_routes
    started, err = time.monotonic(), None
    try:
        req_body = {'model': model(), 'input': text, 'voice': VOICES[voice], 'response_format': 'mp3'}
        if sample_rate():
            req_body['sample_rate'] = sample_rate()
        body = json.dumps(req_body).encode()
        req = urllib.request.Request(speech_url(), data=body, method='POST', headers={
            'Authorization': 'Bearer ' + os.getenv('FLOW_AI_KEY', ''), 'Content-Type': 'application/json', 'User-Agent': 'flow-tts/1.0'})
        with urllib.request.urlopen(req, timeout=int(os.getenv('FLOW_TTS_TIMEOUT', '30'))) as r:
            data = r.read(8_000_001)
        if not 100 < len(data) <= 8_000_000 or not (data[:3] == b'ID3' or data[0] == 0xFF):
            raise ValueError('not an mp3')
        return data
    except Exception as e:
        err = e
        raise
    finally:
        with ai_routes.task('tts'):
            ai_routes.record('tts', model(), started, [], info={'usage': (len(text), 0, 0, 0), 'served': 'cosyvoice-v3-flash'}, exc=err)


def labelled(data, name):
    """The MP3 with its implicit AI label (隐式标识, an ID3 AIGC frame: 《标识办法》第五条). A label that cannot be written
    never costs the reading: the file is kept as it came, and only the exception type is logged."""
    try:
        return aigc_label.mp3(data, 'flow-tts-' + name[:-4])
    except Exception as exc:  # noqa: BLE001
        print('tts: AIGC label not written (%s)' % type(exc).__name__, file=sys.stderr, flush=True)
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


def ensure(c, who, text, voice, cap_left=None, own=False):
    """(url, made) for this sentence in this voice; makes it when it is not stored yet and `who` may.
    who: a learner's id, None for a guest (stored files only), -1 for overnight prewarm (cap_left = that night's budget left).
    own: a sentence of the learner's own article: kept in their own folder, served to them only, with the import caps.
    Raises LookupError (guest, nothing stored), PermissionError (a cap reached), ValueError (bad text), OSError (gateway),
    StoreError (the folder cannot be written: checked before the gateway is paid)."""
    text = norm(text)
    if voice not in VOICES:
        voice = 'us-f'
    if not text or len(text) > MAX_CHARS or not LETTERS.search(text):
        raise ValueError('text')
    name = name_of(text, voice)
    if own and not who:
        raise LookupError('not stored')
    stored = own_file(who, voice, name) if own else file(voice, name)
    where = own_url if own else url
    if stored:
        return where(voice, name), False
    if who is None:
        raise LookupError('not stored')
    n = len(text)
    if who != -1 and (_used(c, who) + n > cap('FLOW_TTS_USER_CHARS') or _used(c, 0) + n > cap('FLOW_TTS_DAILY_CHARS')):
        raise PermissionError('cap')
    if own and _used_import(c, who) + n > cap('FLOW_TTS_IMPORT_CHARS'):
        raise PermissionError('import_cap')
    if own and _used(c, 0) + n > cap('FLOW_TTS_DAILY_CHARS') * cap('FLOW_TTS_IMPORT_PERCENT') / 100:
        raise PermissionError('busy')  # the rest of the day is kept for AI replies and speaking
    if who == -1 and cap_left is not None and n > cap_left:
        raise PermissionError('cap')
    folder = own_dir(who) / voice if own else directory() / voice
    if not (_own_writable(folder) if own else writable(voice)):
        raise StoreError('folder')
    with _lock(str(folder) + name):
        if (folder / name).is_file():  # made by another request while this one waited
            return where(voice, name), False
        try:
            data = _speak(text, voice)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise OSError(str(e)[:120])
        try:
            _store(folder / name, labelled(data, name))
        except OSError as e:
            _warn(folder, e)
            raise StoreError('store')
    _add(c, who, n, 1)
    if who != -1:
        _add(c, 0, n, 1)
    if own:
        c.execute('INSERT INTO tts_import(day, who, chars) VALUES(?,?,?) ON CONFLICT(day, who) DO UPDATE SET chars=chars+excluded.chars', (_day(), who, n))
    c.commit()
    return where(voice, name), True


def post(c, uid, data):
    """POST /api/next/tts {text, voice, pack?}: the stored file's address, made now if need be. Open to guests (stored
    only). With the id of the learner's own article (an import) the sentence must be in it, and is kept for them only."""
    if not enabled():
        return {'error': '服务器朗读没有开启', 'code': 'off'}, 503
    own = _own_pack(c, uid, data.get('pack'))
    if own is False:
        return {'error': '文章不存在'}, 404
    if own is not None and norm(data.get('text')) not in norm(own):
        return {'error': '这段文字不在这篇文章里'}, 400
    try:
        u, made = ensure(c, uid, data.get('text'), data.get('voice') if data.get('voice') in VOICES else 'us-f', own=own is not None)
    except ValueError:
        return {'error': '这段文字不能朗读'}, 400
    except LookupError:
        return {'error': '登录后可以用 AI 朗读', 'code': 'guest'}, 404
    except PermissionError as e:
        if e.args and e.args[0] == 'import_cap':
            return {'error': '今天导入文章的 AI 朗读用完了，明天再试；先用浏览器的声音', 'code': 'import_cap'}, 429
        if e.args and e.args[0] == 'busy':
            return {'error': '今天用 AI 朗读的人多，导入的文章先用浏览器的声音', 'code': 'busy'}, 429
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
    try:
        _daily_tick(db)
    except Exception as e:  # noqa: BLE001  (the night's work below still runs)
        print('tts daily:', type(e).__name__, flush=True)
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
        print('tts prune:', json.dumps(prune()), flush=True)


def prune(days=30, now=None):
    """One-off sentences (an AI's reply, a look-up example) are made on a tap and then rarely heard again: a file older
    than `days` goes, unless it is one of the fixed sentences prewarm keeps (any voice). A pruned sentence is simply
    made again on the next tap. Without this the folder grows by every reply (60–145 KB each)."""
    keep = {name_of(t, v) for v in VOICES for t in fixed_texts()}
    cut = (now or time.time()) - days * 86400
    gone = kept = 0
    for v in VOICES:
        d = directory() / v
        if not d.is_dir():
            continue
        for f in d.glob('*.mp3'):
            try:
                if f.name in keep or f.stat().st_mtime >= cut:
                    kept += 1
                    continue
                f.unlink()
                gone += 1
            except OSError:
                kept += 1
    own_cut = (now or time.time()) - 60 * 86400  # a learner's own articles: two months, then made again when opened
    for f in (Path(__import__('console_ops').data_dir()) / 'tts-own').glob('*/*/*.mp3'):
        try:
            if f.stat().st_mtime < own_cut:
                f.unlink()
                gone += 1
        except OSError:
            pass
    return {'removed': gone, 'kept': kept}


# ---------- 今日热点: its voice ready on the first day ----------
# The day's 热点 article is written at 08:10 (flow-daily, which cannot write the audio folder); a 热点 without a recording is
# read sentence by sentence in the server voice, so the Flow process makes its sentences in the voices learners use within
# a few minutes of it appearing (tick, every 5 minutes), on the overnight budget, one site doing it (a lock file).
_DAILY = {'done': None, 'busy': False}


def daily_texts(c):
    """(id, sentences) of the newest 今日热点 written in the last 36 hours and not narrated; (None, []) otherwise."""
    import next_service as nx
    row = c.execute("SELECT id, content, created FROM lab_packs WHERE origin='daily' ORDER BY created DESC LIMIT 1").fetchone()
    if not row or row[2] < time.time() - 36 * 3600 or __import__('daily_service').retired(json.loads(row[1])):
        return None, []  # none new, or 今日热点 news (paused 2026-11-25)
    try:
        if nx.audio_index()[0].get(row[0]):
            return row[0], []  # it has a recording: nothing to make
    except Exception:  # noqa: BLE001
        pass
    try:
        body = str(json.loads(row[1]).get('body') or '')
    except ValueError:
        body = ''
    return row[0], [s for s in nx.sentences(body) if LETTERS.search(s) and len(s) <= MAX_CHARS]


def _daily_tick(db, inline=False):
    if _DAILY['busy']:
        return
    with db() as c:
        pid, texts = daily_texts(c)
        voices = voices_in_use(c) if texts else []
    if not texts or _DAILY['done'] == pid:
        return
    missing = [(t, v) for v in voices for t in texts if not file(v, name_of(t, v))]
    if not missing:
        _DAILY['done'] = pid
        return
    _DAILY['busy'] = True
    if inline:  # tests
        _daily_make(db, pid, missing)
    else:
        threading.Thread(target=_daily_make, args=(db, pid, missing), daemon=True).start()


def _daily_make(db, pid, missing):
    import fcntl, ai_routes
    try:
        d = directory()
        d.mkdir(parents=True, exist_ok=True)
        with open(d / '.daily.lock', 'w') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return  # the other site is making them
            with db() as c:
                if ai_routes.over_budget(c):
                    return
                left = cap('FLOW_TTS_PREWARM_CHARS') - _used(c, -1)
                for t, v in missing:
                    if len(t) > left:
                        return
                    try:
                        _, made = ensure(c, -1, t, v, cap_left=left)
                        left -= len(t) if made else 0
                    except StoreError:
                        return
                    except (OSError, PermissionError, ValueError):
                        continue
            _DAILY['done'] = pid
    except OSError as e:
        _warn(directory(), e)
    finally:
        _DAILY['busy'] = False


# ---------- 声音接力: made while the reply travels to the page ----------
CONNECT = None  # app.init sets this to its db(); a thread needs a connection of its own
_SOON = threading.BoundedSemaphore(4)  # at most four sentences being made this way at once; past that the page asks itself


def start(uid, text, voice, wait=False):
    """Begin making this sentence in a thread (the page will ask for it in a moment); returns the thread, or None when
    off, nothing to do, or busy. Counts against the learner's share like a tap; any failure is left to the page's request."""
    if not enabled() or not CONNECT or not text or voice not in VOICES or file(voice, name_of(text, voice)):
        return None
    if not _SOON.acquire(blocking=False):
        return None

    def run():
        try:
            c = CONNECT()
            try:
                ensure(c, uid, text, voice)
            finally:
                c.close()
        except Exception:  # the cap, the gateway, the folder: the page's own request says what happened
            pass
        finally:
            _SOON.release()
    t = threading.Thread(target=run, daemon=True)
    t.start()
    if wait:
        t.join()
    return t


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
    import ai_routes
    if ai_routes.over_budget(c):  # the console's daily AI budget is spent: batch work waits for tomorrow (as 例句预生成 does)
        return {'status': 'over-budget'}
    budget = cap('FLOW_TTS_PREWARM_CHARS') if budget is None else budget
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
                ensure(c, -1, t, voice, cap_left=left)
                made += 1
                left -= len(t)
            except StoreError:
                return {'status': 'store', 'made': made, 'stored': stored, 'failed': failed}
            except (OSError, PermissionError, ValueError):
                failed += 1
                if failed >= 5:
                    return {'status': 'gateway', 'made': made, 'stored': stored, 'failed': failed}
    return {'status': 'done', 'made': made, 'stored': stored, 'failed': failed}
