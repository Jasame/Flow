"""Narration and word audio: served by this server, with a Cloudflare R2 bucket as the master copy.

tools/push_media.py uploads the audio to R2 and writes corpus_data/media-manifest.json, which ships with each
release:
  {"v": 1, "version": "<id of this upload>", "narration": {"v5-x": ["us-f", ...]},
   "files": {"us-f/v5-x.m4a": ["<sha256>", <size>], "us-f/v5-x.json": [...], "words/index.json": [...], ...}}

With FLOW_MEDIA_BASE set (the bucket's own domain, e.g. https://media.flowlang.cn):
- a file listed there but missing or different here is fetched once from <base>/audio/<path>, checked against its
  sha256 and size, and kept; from then on this server sends it (this server is the fastest way in from mainland
  China), so audio never has to be copied onto the server by hand;
- the page is told the base (session 'media') and plays from it by itself when this server cannot answer.
Without FLOW_MEDIA_BASE, or without a manifest, nothing is fetched and only the files here are served, as before.
"""
import hashlib, json, os, re, tempfile, threading, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIR = Path(os.getenv('FLOW_AUDIO_DIR') or ROOT / 'audio')
MANIFEST = ROOT / 'corpus_data' / 'media-manifest.json'
MAX_BYTES = 20_000_000
RETRY_AFTER = 60  # seconds before a failed fetch of the same file is tried again
SAFE = re.compile(r'[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9.-]*){0,2}\.(?:m4a|json)')
_M = {'mtime': None, 'data': None}
_STATE = {}   # verified local files: rel -> (mtime_ns, size, sha256)
_FAILED = {}  # rel -> time of the last failed fetch
_LOCKS, _GUARD = {}, threading.Lock()


def base():
    """The media origin, without a trailing slash; https only (plain http only to this machine, for tests)."""
    b = os.getenv('FLOW_MEDIA_BASE', '').strip().rstrip('/')
    return b if b.startswith('https://') or re.fullmatch(r'http://(127\.0\.0\.1|localhost)(:\d{1,5})?', b) else ''


def origin():
    """scheme://host[:port] of the media origin, for the page's Content-Security-Policy; '' when not set."""
    b = base()
    return '/'.join(b.split('/')[:3]) if b else ''


def manifest():
    """The release's media manifest, reloaded when the file changes; None when there is none (or it is broken)."""
    try:
        m = MANIFEST.stat().st_mtime_ns
    except OSError:
        return None
    if _M['mtime'] != m:
        try:
            d = json.loads(MANIFEST.read_text())
            if not isinstance(d.get('files'), dict) or not isinstance(d.get('version'), str) or not d['version']:
                d = None
        except (OSError, ValueError, AttributeError):
            d = None
        _M.update(mtime=m, data=d)
    return _M['data']


def active():
    """The manifest, when R2 is in use (FLOW_MEDIA_BASE set); None otherwise."""
    return manifest() if base() else None


def narration():
    """{material id: [voices]} from the manifest when R2 is in use, else None (the caller reads audio/index.json)."""
    d = active()
    return d.get('narration', {}) if d else None


def version():
    d = active()
    return d['version'] if d else ''


def info():
    """What the page needs for its second line: {'base': '<origin>/audio', 'version': ...}, or None."""
    d = active()
    return {'base': base() + '/audio', 'version': d['version']} if d else None


def path(rel, local=None):
    """Local path of a media file, or None when there is none. rel is its name in the manifest (e.g.
    'us-f/v5-x.m4a', 'words/us/w001.m4a'); local is where the caller keeps it (default DIR/rel).
    A file the manifest lists but that is missing or different here is fetched from R2 first; while R2 cannot be
    reached, an older copy here is still served rather than nothing."""
    if not SAFE.fullmatch(rel or '') or '..' in rel:
        return None
    f = Path(local) if local else DIR / rel
    d = active()
    e = d['files'].get(rel) if d else None
    if not e:
        return f if f.is_file() else None
    sha, size = str(e[0]), int(e[1])
    if _fresh(f, rel, sha, size):
        return f
    with _lock(rel):
        if _fresh(f, rel, sha, size):  # fetched by another request while this one waited
            return f
        if time.time() - _FAILED.get(rel, 0) < RETRY_AFTER:
            return f if f.is_file() else None
        try:
            _fetch(rel, f, sha, size)
        except Exception:
            _FAILED[rel] = time.time()
            return f if f.is_file() else None
        _FAILED.pop(rel, None)
        return f


def _fresh(f, rel, sha, size):
    try:
        st = f.stat()
    except OSError:
        return False
    if st.st_size != size:
        return False
    known = _STATE.get(rel)
    if known and known[0] == st.st_mtime_ns and known[1] == size:
        return known[2] == sha
    h = hashlib.sha256(f.read_bytes()).hexdigest()  # once per file and process (small files)
    _STATE[rel] = (st.st_mtime_ns, size, h)
    return h == sha


def _fetch(rel, f, sha, size):
    req = urllib.request.Request(f'{base()}/audio/{rel}?v={sha[:12]}', headers={'User-Agent': 'flow-media/1.0'})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) != size or hashlib.sha256(data).hexdigest() != sha:
        raise ValueError('media file does not match the manifest')
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
    st = f.stat()
    _STATE[rel] = (st.st_mtime_ns, size, sha)


def _lock(rel):
    with _GUARD:
        return _LOCKS.setdefault(rel, threading.Lock())
