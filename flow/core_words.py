"""Searchable A1–C1 core vocabulary with source-aware examples."""
import json
import re

LEVELS = ('A1', 'A2', 'B1', 'B2', 'C1')
SOURCE = 'https://github.com/X-Trivle/LexiCore'
PAGE_SIZE = 30


def schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS flow_core_terms(
        word TEXT PRIMARY KEY, level TEXT NOT NULL, rank INTEGER NOT NULL,
        meaning TEXT NOT NULL, content TEXT NOT NULL, study_entry TEXT REFERENCES lexicon(id),
        reference TEXT REFERENCES reference_terms(id), has_examples INTEGER NOT NULL)''')
    c.execute('CREATE INDEX IF NOT EXISTS flow_core_band ON flow_core_terms(level,rank)')


def get(c, path, query):
    if path != '/api/vocab/core':
        return None
    q = query.get('q', [''])[0].strip().casefold()
    band = query.get('level', [''])[0]
    scope = query.get('scope', ['all'])[0]
    try:
        page = max(1, int(query.get('page', ['1'])[0]))
    except (TypeError, ValueError):
        return {'error': '页码不正确。'}, 400
    if len(q) > 100 or band not in ('', *LEVELS) or scope not in ('all', 'examples', 'cloze'):
        return {'error': '请检查搜索词、等级或练习筛选。'}, 400
    predicates = []
    args = []
    if q:
        search = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        chinese = re.search(r'[\u3400-\u9fff]', q)
        if chinese:
            predicates.append("(meaning LIKE ? ESCAPE '\\' OR json_extract(content,'$.study_card.meaning') LIKE ? ESCAPE '\\')")
            args.extend(('%' + search + '%',) * 2)
        else:
            predicates.append("word LIKE ? ESCAPE '\\'")
            args.append(search + '%')
    if band:
        predicates.append('level=?')
        args.append(band)
    if scope == 'examples':
        predicates.append('has_examples=1')
    if scope == 'cloze':
        predicates.append("json_type(content,'$.cloze')='object'")
    where = (' WHERE ' + ' AND '.join(predicates)) if predicates else ''
    total = c.execute('SELECT COUNT(*) FROM flow_core_terms' + where, args).fetchone()[0]
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, pages)
    rows = c.execute('SELECT * FROM flow_core_terms' + where +
                     ' ORDER BY level,rank,word LIMIT ? OFFSET ?', (*args, PAGE_SIZE, (page - 1) * PAGE_SIZE))
    items = []
    for row in rows:
        item = json.loads(row['content'])
        item.update(study_entry=row['study_entry'])
        items.append(item)
    count = c.execute('SELECT COUNT(*) FROM flow_core_terms').fetchone()[0]
    return {'items': items, 'total': total, 'core_count': count, 'pages': pages, 'page': page,
            'source': SOURCE}, 200
