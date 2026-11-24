#!/usr/bin/env python3
"""例句预生成: AI example sentences written ahead of time for word-book words that no Flow text uses.

    python3 fill_examples.py [--env-file /etc/flow.env] [--books tem8,gre] [--per-call 16] [--max-calls N]
                             [--pause 1.0] [--dry-run] [--status FILE]

A word card shows up to two sentences from Flow's texts, else the dictionary's example, else an AI example. That last
one is written the first time someone opens the card (the card says 「正在找例句…」 for a few seconds) and is then
cached for everyone in next_word_examples. This writes those AI examples in advance, with the same prompt and the
same checks as the learner's request (vocab_service.example_messages / example_results: a sentence must really use
the word), into the site's own database: FLOW_DATA_DIR of the env file (/etc/flow.env for 语流, /etc/flow-beta.env
for the 内测版). The model is the site's own (FLOW_AI_* / FLOW_TEXT_AI_MODEL of the env file); the calls show in the
AI gateway's console under the site's key, not in any learner's daily count.

A word that already has an example of any kind is skipped, so a run can stop and start again; every word is asked
for once. Books go in the order given (default: the exam and data books first, then the frequency books). It prints
progress every 20 calls and stops after 5 failed calls in a row. Exit status 0 when nothing is left to do, 1 when
words are left (stopped early or --max-calls reached), 2 when no model is configured.

Run it in the background on the server, e.g.
    cd /www/wwwroot/flow && nohup python3 fill_examples.py > /root/claude-ops/fill-examples.log 2>&1 &
or from the xmc.hk console (运维 → 后台任务, r26), which starts it with --status and shows that file's progress:
{state: running | done | left | no-model, total, looked, calls, made, left, books, updated}.
"""
import argparse, json, os, sqlite3, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = ('zk', 'gk', 'cet4', 'cet6', 'ky', 'tem4', 'ielts', 'tem8', 'toefl', 'gre', 'nawl', 'bsl', 'core', 'mid', 'high', 'adv', 'ext')
EASY = {'core', 'mid', 'zk', 'gk', 'cet4'}  # books whose examples are written for B1 learners; the rest for B2


def pending(c, vs, books):
    """[(book, level, word)] still without any example, each word once, in book order and frequency order."""
    seen, out = set(), []
    words = vs.book_words()
    for b in books:
        for _, w in words.get(b, []):
            if w in seen:
                continue
            seen.add(w)
            if vs.needs_example(c, w):
                out.append((b, 'B1' if b in EASY else 'B2', w))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description='例句预生成：给词书里没有例句的词提前写好 AI 例句')
    ap.add_argument('--env-file', default='/etc/flow.env')
    ap.add_argument('--books', help='只做这几本（逗号分隔，按这个顺序）')
    ap.add_argument('--per-call', type=int, default=16, help='每次请求写几个词（默认 16）')
    ap.add_argument('--max-calls', type=int, default=0, help='最多请求几次（默认不限）')
    ap.add_argument('--pause', type=float, default=1.0, help='两次请求之间停几秒')
    ap.add_argument('--dry-run', action='store_true', help='只数还缺多少，不请求')
    ap.add_argument('--status', help='把进度写进这个 JSON 文件（后台的「后台任务」读它）')
    a = ap.parse_args(argv)
    status = {'state': 'running', 'books': [], 'total': None, 'looked': 0, 'calls': 0, 'made': 0, 'left': None}

    def report(**kw):
        if not a.status:
            return
        status.update(kw, updated=time.time())
        tmp = Path(a.status + '.tmp')
        tmp.write_text(json.dumps(status, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, a.status)
    if Path(a.env_file).is_file():
        sys.path.insert(0, str(HERE))
        from studio_setup import read_env
        for k, v in read_env(Path(a.env_file).read_text()).items():
            if k.startswith(('FLOW_', 'GOOGLE_')):
                os.environ[k] = v
    sys.path.insert(0, str(HERE))
    import vocab_service as vs
    from vertex_auth import ai_enabled
    from chat_service import request_model
    from lab_service import parse
    db = Path(os.environ.get('FLOW_DATA_DIR') or HERE / 'data') / 'flow.sqlite3'
    if not db.is_file():
        print(f'找不到网站数据库：{db}')
        return 2
    c = sqlite3.connect(db, timeout=15)
    c.row_factory = sqlite3.Row
    books = [b for b in (a.books.split(',') if a.books else ORDER) if b in vs.book_words()]
    todo = pending(c, vs, books)
    print(f'{db}: {len(todo)} words without an example in {",".join(books)} ({(len(todo) + a.per_call - 1) // max(1, a.per_call)} calls)', flush=True)
    report(books=books, total=len(todo), left=len(todo))
    if a.dry_run or not todo:
        report(state='done' if not todo else 'left')
        return 0 if not todo else 1
    if not ai_enabled():
        print('没有配置 AI 模型（FLOW_AI_MODEL 等），不能写例句。')
        report(state='no-model')
        return 2
    calls = made = fails = 0
    i = 0
    while i < len(todo):
        if a.max_calls and calls >= a.max_calls:
            break
        level = todo[i][1]
        batch = []
        while i < len(todo) and len(batch) < a.per_call and todo[i][1] == level:
            if vs.needs_example(c, todo[i][2]):  # a learner may have opened the card meanwhile
                batch.append(todo[i][2])
            i += 1
        if not batch:
            continue
        calls += 1
        try:
            reply, _ = request_model(vs.example_messages(batch, level))
            out = vs.example_results(parse(reply), batch)
            vs.save_examples(c, out)
            made += len(out)
            fails = 0
        except Exception as exc:  # noqa: BLE001 - one failed call is logged and the run goes on
            fails += 1
            print(f'call {calls} failed ({type(exc).__name__}: {str(exc)[:120]})', flush=True)
            if fails >= 5:
                print('5 failed calls in a row: stopping; run again later to go on.', flush=True)
                break
            time.sleep(10)
        if calls % 20 == 0:
            print(f'{calls} calls, {made} examples written, {i}/{len(todo)} words looked at', flush=True)
        report(looked=i, calls=calls, made=made)
        time.sleep(a.pause)
    left = len(pending(c, vs, books))
    print(f'done: {calls} calls, {made} examples written, {left} words still without an example', flush=True)
    report(state='done' if not left else 'left', looked=i, calls=calls, made=made, left=left)
    return 0 if not left else 1


if __name__ == '__main__':
    sys.exit(main())
