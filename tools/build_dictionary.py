#!/usr/bin/env python3
"""Prebuild Flow's dictionary into flow/corpus_data/dictionary-flow.json.

    python3 tools/build_dictionary.py           # rebuild after changing any of its sources
    python3 tools/build_dictionary.py --check   # exit 1 if the file is out of date (the tests run this)

Sources: yl-reference.json, ecdict-flow.json, meaning-fixes.json, irregular-flow.json (next_service.DICT_SOURCES).
Building from them parses ~38 MB of JSON (a ~48 MB peak the server process keeps as resident memory); the app
loads this compact file instead: one row per word, fields in next_service.DICT_FIELDS order.
"""
import json, sys
from pathlib import Path

FLOW = Path(__file__).resolve().parents[1] / 'flow'
sys.path.insert(0, str(FLOW))
import next_service as nx  # noqa: E402

built = nx.build_dictionary()
rows = {k: [int(e[f]) if f == 'ref' else e[f] for f in nx.DICT_FIELDS] for k, e in built.items()}
doc = json.dumps({'notice': 'Built by tools/build_dictionary.py from ' + ', '.join(nx.DICT_SOURCES) + '; ECDICT (MIT) and the yl reference list. Do not edit.',
                  'fields': list(nx.DICT_FIELDS), 'words': rows}, ensure_ascii=False, separators=(',', ':')) + '\n'
if '--check' in sys.argv:
    if not nx.DICT_FILE.exists() or nx.DICT_FILE.read_text(encoding='utf-8') != doc:
        sys.exit('dictionary-flow.json is out of date with its sources: run python3 tools/build_dictionary.py')
else:
    nx.DICT_FILE.write_text(doc, encoding='utf-8')
    print(f'{len(rows)} words -> {nx.DICT_FILE.name} ({nx.DICT_FILE.stat().st_size:,} bytes)')
