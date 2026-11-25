"""更新记录 for learners (2026-11-25): what each 语流 release changed, in plain words.

The data is corpus_data/updates.json, written with each production release (docs/releases.md, 「怎么续写」): one entry per
release, newest first, with the sentences grouped as 新功能 (new), 改进 (better) and 修好的问题 (fixed), an optional note,
and two or three highlights for 今日's 「语流更新了」 card. The id is the internal tag (r30): it keys 「seen」 on the phone and
is never shown; the label (「11 月 25 日下午」) is. The beta block lists what is on the 内测版 and not on 语流 yet; only the
内测版 (FLOW_CHANNEL=beta) returns it. FLOW_UPDATES_FILE points elsewhere (the UI test server: none, so 今日 shows no card).
"""
import json, os, re
from pathlib import Path

FILE = Path(__file__).resolve().parent / 'corpus_data' / 'updates.json'
GROUPS = ('new', 'better', 'fixed')
_cache = {}


def _path():
    return Path(os.getenv('FLOW_UPDATES_FILE') or FILE)


def _beta():
    return os.getenv('FLOW_CHANNEL', '').strip().lower() == 'beta'


def load():
    """The data file, read again only when it changes; a missing or broken file is no updates (never an error)."""
    p = _path()
    try:
        key = (str(p), p.stat().st_mtime_ns)
    except OSError:
        return {'released': [], 'beta': None}
    if _cache.get('key') != key:
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
        released = [e for e in data.get('released') or [] if isinstance(e, dict) and e.get('id') and e.get('label')]
        _cache.update(key=key, data={'released': released, 'beta': data.get('beta')})
    return _cache['data']


def _entry(e):
    out = {k: e[k] for k in ('id', 'date', 'label') if k in e}
    for g in GROUPS:
        out[g] = [str(s) for s in e.get(g) or []]
    if e.get('note'):
        out['note'] = str(e['note'])
    return out


def listing():
    """GET /api/next/updates: every release, newest first; the beta block on the 内测版 only."""
    d = load()
    beta = d.get('beta') if _beta() else None
    if beta and not any(beta.get(g) for g in GROUPS):
        beta = None
    return {'released': [_entry(e) for e in d['released']],
            'beta': ({'date': beta.get('date', ''), **{g: [str(s) for s in beta.get(g) or []] for g in GROUPS}} if beta else None)}


def latest():
    """The newest release, for 今日's card (in /api/next/home): its id, label and two or three highlights."""
    d = load()
    if not d['released']:
        return None
    e = d['released'][0]
    hl = [str(s) for s in e.get('highlights') or []] or [s for g in GROUPS for s in e.get(g) or []]
    return {'id': e['id'], 'label': e['label'], 'highlights': hl[:3]}


# Words that do not belong in a learner's 更新记录 (tests/test_updates.py): PR numbers, tags, model and vendor names.
# Case matters: r30 and b12 are tags, B2 and C1 are levels.
TECH = re.compile(r'#\d|\b[rb]\d+\b|\bPR\b|DeepSeek|Gemini|Qwen|Omni|CosyVoice|Kokoro|百炼|通义|千问|\bAPI\b|e2e|\bbeta\b|commit')
