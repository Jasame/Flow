#!/usr/bin/env python3
"""例句预生成: AI example sentences written ahead of time for word-book words that no Flow text uses.

    python3 fill_examples.py [--env-file /etc/flow.env] [--books tem8,gre] [--per-call 16] [--max-calls N]
                             [--workers 8] [--pause 1.0] [--max-yuan 5] [--dry-run] [--status FILE] [--offpeak]

A word card shows up to two sentences from Flow's texts, else the dictionary's example, else an AI example. That last
one is written the first time someone opens the card (the card says 「正在找例句…」 for a few seconds) and is then
cached for everyone in next_word_examples. This writes those AI examples in advance, with the same prompt and the
same checks as the learner's request (vocab_service.example_messages / example_results: a sentence must really use
the word), into the site's own database: FLOW_DATA_DIR of the env file (/etc/flow.env for 语流, /etc/flow-beta.env
for the 内测版). The model is the site's own (FLOW_AI_* / FLOW_TEXT_AI_MODEL of the env file); the calls show in the
AI gateway's console under the site's key, not in any learner's daily count.

A word that already has an example of any kind is skipped, so a run can stop and start again; every word is asked
for once. Books go in the order given (default: the exam and data books first, then the frequency books). It prints
progress every 20 calls and stops after 4 + --workers failed calls in a row (5 for one at a time). Exit status 0
when nothing is left to do, 1 when words are left (stopped early, --max-calls or --max-yuan reached), 2 when no model
is configured.

--workers N (2026-11-25, the owner: 「直接调用 deepseek 可以高并发，很快就结束了」): N calls at once, each in a thread
of its own; only the main thread reads and writes the database (SQLite has one writer at a time): each answer is
checked and committed there as it comes in. (Each call's own ai_calls row is one short INSERT by ai_routes.record,
as in the site.) A rate limit (429), a server error (5xx), a timeout or a network error halves the calls at once
and makes the next one wait (5 s, then 10, 20 … up to 2 minutes), and that batch is asked again (3 tries); after 10
answers in a row one more call runs at once again, up to N. The xmc-api gateway takes 20 requests at once in all
(learners included): keep N at 16 or less; 8 first, then about 12. --pause is the wait between starting two calls
(default 1 s one at a time, 0.25 s with --workers). 百炼's own limit for deepseek-v4.1-flash in 华北2（北京）
(help.aliyun.com/zh/model-studio/rate-limit, updated 2026-11-23, read 2026-11-25): dynamic, at least 1.2 million
tokens a minute (input and output) for the whole account (the other regions' table: 15,000 calls a minute); 12 calls
of a few thousand tokens each every 10-15 s is far below it, so the gateway's 20 is the limit that matters.
On a batch line of its own (a route other than the site's default model, e.g. flow-batch-ds-flash), a call goes to
that line only: no fallback to the main model, so the run pays where it was meant to and a rate limit comes back here
to slow down. On the default model it is the site's usual request_model.
--max-yuan X: start no new call once the calls of this run cost X yuan (ai_calls, priced as the console prices them:
ai_routes.cost); the status file and the last line say what the run cost.

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
      <python3.11 of the flow service> fill_examples.py --env-file /dev/null --status /tmp/flow-fill/status.json --workers 8

(The examples' route follows AI 例句's, in the batch lane. To send only this run to a line of its own, add
-p Environment=FLOW_AI_ROUTES=next-examples=flow-batch-ds-flash: the site itself keeps its routes.)

(--env-file /dev/null: the environment already comes from systemd. For the 内测版: /etc/flow-beta.env and
/www/wwwroot/flow-beta. Add --wait to stay until it ends; try --dry-run and --max-calls 5 first, as on b5, 2026-11-24.)
Or start it from the xmc.hk console (运维 → 后台任务, r26), which runs it as the site does, with --status, and shows
that file's progress: {state: running | waiting | done | left | budget | no-model, total, looked, calls, made, left, other_sense, books, updated,
until, workers, at_once, failed, yuan}.

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


class Pace:
    """How many calls run at once: --workers, halved on a rate limit or a server error (and the next call waits 5 s,
    10 s, 20 s … up to 2 minutes), one more again after 10 answers in a row."""

    def __init__(self, most):
        self.most = self.now = max(1, most)
        self.wins = self.errors = 0
        self.hold = 0.0  # seconds to wait before the next call starts

    def ok(self):
        self.errors, self.wins = 0, self.wins + 1
        if self.wins >= 10 and self.now < self.most:
            self.now, self.wins = self.now + 1, 0

    def slow(self):
        self.wins, self.errors = 0, self.errors + 1
        self.now = max(1, self.now // 2)
        self.hold = max(self.hold, min(120, 5 * 2 ** (self.errors - 1)))


def ask(messages):
    """One call for this run (in its worker thread, inside ai_routes.task('fill-examples')): the reply text."""
    import ai_routes, chat_service
    model = ai_routes.route()
    if model == ai_routes.default_model() or not chat_service.text_provider(model):
        return chat_service.request_model(messages)[0]  # the site's default model: its usual call
    # a batch line of its own: that line only (see the docstring), written to ai_calls the way request_model does
    ai_routes.CTX.route = model
    chat_service.INFO.__dict__.clear()
    started = time.monotonic()
    try:
        reply = chat_service._request_text_service(messages, model, ai_routes.extra_body(model))[0]
    except Exception as exc:
        ai_routes.record('text', model, started, messages, None, dict(chat_service.INFO.__dict__), exc)
        raise
    ai_routes.record('text', model, started, messages, reply, dict(chat_service.INFO.__dict__))
    return reply


def spent(c, since):
    """Yuan the calls of this run cost so far (ai_calls rows of 例句预生成 since it started, as the console prices them)."""
    import ai_routes
    try:
        rows = c.execute("SELECT served, model, ts, prompt, cached, completion FROM ai_calls WHERE kind='fill-examples' AND ts>=?", (since,)).fetchall()
    except sqlite3.Error:
        return 0.0
    return sum(ai_routes.cost(ai_routes.served_name(s, m), t, p, k, o) for s, m, t, p, k, o in rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description='例句预生成：给词书里没有例句的词提前写好 AI 例句')
    ap.add_argument('--env-file', default='/etc/flow.env')
    ap.add_argument('--books', help='只做这几本（逗号分隔，按这个顺序）')
    ap.add_argument('--per-call', type=int, default=16, help='每次请求写几个词（默认 16）')
    ap.add_argument('--max-calls', type=int, default=0, help='最多请求几次（默认不限）')
    ap.add_argument('--workers', type=int, default=1, help='同时发几个请求（默认 1；网关一共只接 20 个，别超过 16）')
    ap.add_argument('--pause', type=float, default=None, help='两次请求开始之间停几秒（默认一次一个时 1 秒，并发时 0.25 秒）')
    ap.add_argument('--max-yuan', type=float, default=0, help='这次运行花到这么多元就不再发新请求（默认不限）')
    ap.add_argument('--dry-run', action='store_true', help='只数还缺多少，不请求')
    ap.add_argument('--status', help='把进度写进这个 JSON 文件（后台的「后台任务」读它）')
    ap.add_argument('--offpeak', action='store_true', help='例句用的模型有忙时价（百炼上的 DeepSeek：北京时间 8–22 点）时，等到半价时段再跑')
    a = ap.parse_args(argv)
    a.workers = max(1, min(16, a.workers))
    pause = a.pause if a.pause is not None else (1.0 if a.workers == 1 else 0.25)
    status = {'state': 'running', 'books': [], 'total': None, 'looked': 0, 'calls': 0, 'made': 0, 'other_sense': 0, 'left': None,
              'workers': a.workers}

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
    from chat_service import transient
    from lab_service import parse
    import ai_routes
    from collections import deque
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
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
    calls = made = fails = failed = other = 0
    d = __import__('next_service').dictionary()
    since, pace, again, running, stop = time.time(), Pace(a.workers), deque(), {}, None
    i = 0

    def take():
        """The next batch: words of one level, each still without an example (a learner may have opened the card)."""
        nonlocal i
        if again:
            return again.popleft()
        while i < len(todo):
            level, batch = todo[i][1], []
            while i < len(todo) and len(batch) < a.per_call and todo[i][1] == level:
                if vs.needs_example(c, todo[i][2]):
                    batch.append(todo[i][2])
                i += 1
            if batch:
                return batch, level, 1
        return None

    def work(messages):
        with ai_routes.task('fill-examples'):
            return ask(messages)
    pool = ThreadPoolExecutor(a.workers)
    try:
        while True:
            if pace.hold and stop is None:  # after a rate limit: no new call for a while (those under way go on)
                time.sleep(pace.hold)
                pace.hold = 0.0
            # start calls while there is room
            while stop is None and len(running) < pace.now:
                if a.max_calls and calls >= a.max_calls:
                    stop = 'max-calls'
                    break
                if ai_routes.over_budget():
                    print('今天的 AI 预算已用完：停下，明天再跑。', flush=True)
                    stop = 'budget'
                    break
                if a.max_yuan and spent(c, since) >= a.max_yuan:
                    print(f'这次已经花了 ¥{spent(c, since):.2f}，到了 --max-yuan {a.max_yuan:g}：停下。', flush=True)
                    stop = 'max-yuan'
                    break
                line = ai_routes.price_of(ai_routes.usual_models().get(ai_routes.route('fill-examples'), ''))
                if a.offpeak and ai_routes.busy(time.time(), line):
                    if running:
                        break  # let the calls under way finish, then wait
                    until = ai_routes.next_quiet(time.time(), line)
                    report(state='waiting', until=until)
                    time.sleep(min(600, max(5, until - time.time())))
                    continue
                nxt = take()
                if nxt is None:
                    break
                batch, level, tries = nxt
                calls += 1
                running[pool.submit(work, vs.example_messages(batch, level))] = nxt
                report(state='running', until=None, calls=calls, at_once=pace.now)
                if pause:
                    time.sleep(pause)
            if not running:
                if stop or (not again and i >= len(todo)):
                    break
                continue  # a rate limit's wait first (pace.hold), then more calls
            done, _ = wait(running, timeout=5, return_when=FIRST_COMPLETED)
            for f in done:
                batch, level, tries = running.pop(f)
                try:
                    reply = f.result()
                    out = vs.example_results(parse(reply), batch)
                except Exception as exc:  # noqa: BLE001 - one failed call is logged and the run goes on
                    fails, failed = fails + 1, failed + 1
                    retry = transient(exc)
                    print(f'call failed ({type(exc).__name__}: {str(exc)[:120]})' + (f'; {len(batch)} words asked again later' if retry and tries < 3 else ''), flush=True)
                    if retry:
                        pace.slow()
                        if tries < 3:
                            again.append((batch, level, tries + 1))
                    if fails >= 4 + a.workers and stop is None:
                        print(f'{fails} failed calls in a row: stopping; run again later to go on.', flush=True)
                        stop = 'failing'
                    continue
                vs.save_examples(c, out)  # this thread is the only one that writes examples
                made += len(out)
                fails = 0
                pace.ok()
                # an example in another sense than the first: counted, so a run shows how often the model chose to
                other += sum(1 for w, e in out.items() if e.get('sense') and vs.first_sense(d[w]['meaning']) not in e['sense'])
                answered = calls - len(running) - failed
                if answered % 20 == 0:
                    print(f'{calls} calls, {made} examples written, {i}/{len(todo)} words looked at, {pace.now} at once', flush=True)
                report(looked=i, calls=calls, made=made, other_sense=other, failed=failed, at_once=pace.now, yuan=round(spent(c, since), 4))
    finally:
        pool.shutdown(wait=True)
    left = len(pending(c, vs, books))
    yuan = spent(c, since)
    print(f'done: {calls} calls ({failed} failed), {made} examples written ({other} in another sense than the first), '
          f'{left} words still without an example, ¥{yuan:.2f}', flush=True)
    state = 'budget' if stop == 'budget' else 'done' if not left else 'left'
    report(state=state, looked=i, calls=calls, made=made, other_sense=other, failed=failed, left=left, yuan=round(yuan, 4))
    return 0 if not left else 1


if __name__ == '__main__':
    sys.exit(main())
