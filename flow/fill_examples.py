#!/usr/bin/env python3
"""例句预生成: AI example sentences written ahead of time for word-book words that no Flow text uses.

    python3 fill_examples.py [--env-file /etc/flow.env] [--books tem8,gre] [--per-call 16] [--max-calls N]
                             [--pause 1.0] [--dry-run] [--status FILE] [--offpeak]

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

--offpeak: when the model the examples' route usually reaches has busy hours (DeepSeek on 百炼: 08:00–22:00 Beijing
time; half price the rest of the day), wait them out. Qwen models have none (their half price is 百炼's batch API).
The calls take the batch lane (ai_routes): flow-batch-X for the examples' flow-text-X where the gateway has it. It also
stops for the day once the console's daily AI budget is spent (state budget); run it again tomorrow. Every call is in ai_calls as 例句预生成（批量）.

On the server, run it as the site's own user (www), never as root. The database is in WAL mode: a root process can
leave root-owned flow.sqlite3-wal / -shm files behind, and then the site (running as www) can no longer write to its
own database. The env file is readable by root only, so let systemd read it and start the script as www, with the
site's interpreter (systemctl show flow -p ExecStart) and a folder www can write for the log and status:

    mkdir -p /tmp/flow-fill && chown www:www /tmp/flow-fill
    systemd-run --collect --unit=flow-fill --uid=www --gid=www -p EnvironmentFile=/etc/flow.env \
      --working-directory=/www/wwwroot/flow -p StandardOutput=append:/tmp/flow-fill/run.log -p StandardError=append:/tmp/flow-fill/run.log \
      <python3.11 of the flow service> fill_examples.py --env-file /dev/null --status /tmp/flow-fill/status.json

(--env-file /dev/null: the environment already comes from systemd. For the 内测版: /etc/flow-beta.env and
/www/wwwroot/flow-beta. Add --wait to stay until it ends; try --dry-run and --max-calls 5 first, as on b5, 2026-11-24.)
Or start it from the xmc.hk console (运维 → 后台任务, r26), which runs it as the site does, with --status, and shows
that file's progress: {state: running | waiting | done | left | budget | no-model, total, looked, calls, made, left, other_sense, books, updated,
until}.

Each word is written at its own level (vocab_service.example_level: the school and basic books A2, 四级 B1, the rest
B2), in its first sense unless that one is clearly a rare use; the sense used is kept with the example.
"""
import argparse, json, os, sqlite3, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = ('zk', 'gk', 'cet4', 'cet6', 'ky', 'tem4', 'ielts', 'tem8', 'toefl', 'gre', 'nawl', 'bsl', 'core', 'mid', 'high', 'adv', 'ext')


def pending(c, vs, books):
    """[(book, level, word)] still without any example, each word once, in book order; within a book by level (so a
    call takes words of one level) and then by frequency."""
    seen, out = set(), []
    words = vs.book_words()
    for b in books:
        mine = []
        for _, w in words.get(b, []):
            if w in seen:
                continue
            seen.add(w)
            if vs.needs_example(c, w):
                mine.append((b, vs.example_level(w), w))
        out += sorted(mine, key=lambda x: x[1])  # stable: frequency order kept within a level
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
    ap.add_argument('--offpeak', action='store_true', help='例句用的模型有忙时价（百炼上的 DeepSeek：北京时间 8–22 点）时，等到半价时段再跑')
    a = ap.parse_args(argv)
    status = {'state': 'running', 'books': [], 'total': None, 'looked': 0, 'calls': 0, 'made': 0, 'other_sense': 0, 'left': None}

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
    import ai_routes
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
    calls = made = fails = other = 0
    d = __import__('next_service').dictionary()
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
        if ai_routes.over_budget():
            print('今天的 AI 预算已用完：停下，明天再跑。', flush=True)
            report(state='budget', looked=i, calls=calls, made=made)
            return 1
        line = ai_routes.price_of(ai_routes.usual_models().get(ai_routes.route('fill-examples'), ''))
        while a.offpeak and ai_routes.busy(time.time(), line):
            until = ai_routes.next_quiet(time.time(), line)
            report(state='waiting', until=until)
            time.sleep(min(600, max(5, until - time.time())))
        report(state='running', until=None)
        calls += 1
        try:
            with ai_routes.task('fill-examples'):
                reply, _ = request_model(vs.example_messages(batch, level))
            out = vs.example_results(parse(reply), batch)
            vs.save_examples(c, out)
            made += len(out)
            # an example in another sense than the first: counted, so a run shows how often the model chose to
            other += sum(1 for w, e in out.items() if e.get('sense') and vs.first_sense(d[w]['meaning']) not in e['sense'])
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
        report(looked=i, calls=calls, made=made, other_sense=other)
        time.sleep(a.pause)
    left = len(pending(c, vs, books))
    print(f'done: {calls} calls, {made} examples written ({other} in another sense than the first), {left} words still without an example', flush=True)
    report(state='done' if not left else 'left', looked=i, calls=calls, made=made, other_sense=other, left=left)
    return 0 if not left else 1


if __name__ == '__main__':
    sys.exit(main())
