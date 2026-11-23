#!/usr/bin/env python3
"""Uploads Flow's audio to the Cloudflare R2 bucket and writes flow/corpus_data/media-manifest.json.

    python3 tools/push_media.py <audio dir> [--dry-run] [--all] [--verify https://media.flowlang.cn]

<audio dir> is what tools/gen_audio.py and tools/gen_word_audio.py write:
  index.json, us-f/ us-m/ uk-f/ uk-m/ (<id>.m4a + <id>.json), words/index.json, words/us/ words/uk/ (<sprite>.m4a)

Only files that are new or changed since the manifest in the repository are uploaded (--all: every file). Objects go
to audio/<path> with their content type and a year of browser caching; every URL carries ?v=<content> so a changed
file is never served from an old cache. The manifest (sha256 and size of every file, the narration index, and an id
of this upload) is then rewritten; commit it, and the next release tells the server what to fetch (flow/media.py).

Credentials (an R2 API token with Object Read & Write on this bucket only), from the environment or --env-file,
default ~/.config/flow/r2.env (mode 600, never committed):
  R2_ACCOUNT_ID=…  R2_BUCKET=flow-media  R2_ACCESS_KEY_ID=…  R2_SECRET_ACCESS_KEY=…
Nothing secret is ever printed. Uses only the Python standard library (AWS Signature Version 4, which R2 accepts).
"""
import argparse, datetime, hashlib, hmac, json, os, random, sys, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'flow' / 'corpus_data' / 'media-manifest.json'
VOICES = ('us-f', 'us-m', 'uk-f', 'uk-m')
TYPES = {'.m4a': 'audio/mp4', '.json': 'application/json'}
CACHE = 'public, max-age=31536000'
KEYS = ('R2_ACCOUNT_ID', 'R2_BUCKET', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY')


# ---------------------------------------------------------------- AWS Signature Version 4 (S3, R2)

def _hmac(key, text):
    return hmac.new(key, text.encode(), hashlib.sha256).digest()


def authorization(method, host, path, headers, payload_sha, amz_date, key_id, secret, region='auto', service='s3', query=''):
    """The Authorization header for one request. headers: those to sign besides host, x-amz-date and
    x-amz-content-sha256 (lower-case names). path is already URI-encoded."""
    signed = {'host': host, 'x-amz-content-sha256': payload_sha, 'x-amz-date': amz_date, **{k.lower(): v for k, v in headers.items()}}
    names = sorted(signed)
    canonical = '\n'.join([method, path, query, ''.join(f'{k}:{" ".join(str(signed[k]).split())}\n' for k in names),
                           ';'.join(names), payload_sha])
    day = amz_date[:8]
    scope = f'{day}/{region}/{service}/aws4_request'
    to_sign = '\n'.join(['AWS4-HMAC-SHA256', amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(('AWS4' + secret).encode(), day), region), service), 'aws4_request')
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return f'AWS4-HMAC-SHA256 Credential={key_id}/{scope}, SignedHeaders={";".join(names)}, Signature={signature}'


def put(cfg, key, body, content_type):
    endpoint = cfg.get('R2_ENDPOINT') or f'https://{cfg["R2_ACCOUNT_ID"]}.r2.cloudflarestorage.com'
    host = urllib.parse.urlsplit(endpoint).netloc
    path = '/' + urllib.parse.quote(f'{cfg["R2_BUCKET"]}/{key}', safe='/-_.~')
    sha = hashlib.sha256(body).hexdigest()
    amz_date = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    extra = {'content-type': content_type, 'cache-control': CACHE}
    auth = authorization('PUT', host, path, extra, sha, amz_date, cfg['R2_ACCESS_KEY_ID'], cfg['R2_SECRET_ACCESS_KEY'])
    req = urllib.request.Request(endpoint + path, data=body, method='PUT', headers={
        'Authorization': auth, 'x-amz-date': amz_date, 'x-amz-content-sha256': sha, 'Content-Type': content_type, 'Cache-Control': CACHE})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if r.status not in (200, 201):
                    raise RuntimeError(f'HTTP {r.status}')
                return
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise SystemExit(f'R2 refused the upload (HTTP {e.code}): check the token in the env file and that it can write to this bucket')
            if attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise


# ---------------------------------------------------------------- what to upload

def collect(src):
    """{path in the bucket under audio/: local file} for everything the site serves."""
    out = {}
    for v in VOICES:
        for f in sorted((src / v).glob('v5-*')):
            if f.suffix in ('.m4a', '.json') and f.is_file():
                out[f'{v}/{f.name}'] = f
    if (src / 'words' / 'index.json').is_file():
        out['words/index.json'] = src / 'words' / 'index.json'
    for accent in ('us', 'uk'):
        for f in sorted((src / 'words' / accent).glob('*.m4a')):
            out[f'words/{accent}/{f.name}'] = f
    return out


def describe(files):
    return {rel: [hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_size] for rel, f in files.items()}


def narration_index(src, listed):
    """{material id: [voices]}: from <src>/index.json, keeping a voice only when its audio and timings are both there."""
    try:
        index = json.loads((src / 'index.json').read_text())
    except (OSError, ValueError):
        index = {}
    out = {}
    for pid, voices in sorted(index.items()):
        ok = [v for v in voices if f'{v}/{pid}.m4a' in listed and f'{v}/{pid}.json' in listed]
        if ok:
            out[pid] = ok
    return out


def build_manifest(src, described):
    version = hashlib.sha256(json.dumps(described, sort_keys=True).encode()).hexdigest()[:12]
    return {'v': 1, 'version': version, 'narration': narration_index(src, described), 'files': dict(sorted(described.items()))}


def read_env(path):
    out = {}
    try:
        for line in Path(path).expanduser().read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def verify(base, manifest, sample=6):
    """Fetch a few files through the public domain: same bytes as listed, and CORS for the site's own origins."""
    problems = []
    rels = random.Random(1).sample(sorted(manifest['files']), min(sample, len(manifest['files'])))
    for rel in rels:
        sha, size = manifest['files'][rel]
        url = f'{base.rstrip("/")}/audio/{rel}?v={sha[:12]}'
        try:
            req = urllib.request.Request(url, headers={'Origin': 'https://flow.jasa.hk', 'User-Agent': 'flow-media/1.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                data, allow = r.read(), r.headers.get('Access-Control-Allow-Origin', '')
        except Exception as e:
            problems.append(f'{rel}: {type(e).__name__} {getattr(e, "code", "")}'); continue
        if len(data) != size or hashlib.sha256(data).hexdigest() != sha:
            problems.append(f'{rel}: different bytes')
        if rel.endswith('.json') and allow not in ('*', 'https://flow.jasa.hk'):
            problems.append(f'{rel}: no CORS for https://flow.jasa.hk (set the bucket CORS policy)')
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src', type=Path)
    ap.add_argument('--dry-run', action='store_true', help='show what would be uploaded; upload and write nothing')
    ap.add_argument('--all', action='store_true', help='upload every file, not only new or changed ones')
    ap.add_argument('--env-file', default='~/.config/flow/r2.env')
    ap.add_argument('--verify', metavar='BASE', help='after uploading, check a few files through this public domain')
    ap.add_argument('--manifest', type=Path, default=MANIFEST)
    a = ap.parse_args(argv)
    files = collect(a.src)
    if not files:
        raise SystemExit(f'no audio found in {a.src}')
    described = describe(files)
    try:
        old = json.loads(a.manifest.read_text()).get('files', {})
    except (OSError, ValueError):
        old = {}
    todo = sorted(rel for rel in described if a.all or old.get(rel) != described[rel])
    size = sum(described[rel][1] for rel in todo)
    print(f'{len(described)} files, {len(todo)} to upload ({size / 1e6:.1f} MB)', flush=True)
    if a.dry_run:
        for rel in todo[:20]:
            print('  ' + rel)
        if len(todo) > 20:
            print(f'  … and {len(todo) - 20} more')
        return 0
    cfg = {**read_env(a.env_file), **{k: os.environ[k] for k in (*KEYS, 'R2_ENDPOINT') if os.environ.get(k)}}
    missing = [k for k in KEYS if not cfg.get(k)]
    if missing and todo:
        raise SystemExit('missing in the environment or ' + a.env_file + ': ' + ', '.join(missing))
    done = 0

    def one(rel):
        f = files[rel]
        put(cfg, 'audio/' + rel, f.read_bytes(), TYPES[f.suffix])
        return rel

    with ThreadPoolExecutor(8) as pool:
        for _ in pool.map(one, todo):
            done += 1
            if done % 100 == 0 or done == len(todo):
                print(f'  uploaded {done}/{len(todo)}', flush=True)
    manifest = build_manifest(a.src, described)
    a.manifest.parent.mkdir(parents=True, exist_ok=True)
    a.manifest.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f'manifest {a.manifest.relative_to(ROOT) if a.manifest.is_relative_to(ROOT) else a.manifest}: version {manifest["version"]}, '
          f'{len(manifest["narration"])} materials with narration')
    if a.verify:
        problems = verify(a.verify, manifest)
        print('verify: ' + ('OK' if not problems else 'problems:\n  ' + '\n  '.join(problems)))
        return 1 if problems else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
