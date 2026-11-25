#!/usr/bin/env python3
"""Flow 的发布总账：从 git 里把每次发布的内容整理成一段文字（标准库，Python 3.9 以上）。

    python3 tools/changelog.py draft <从> <到>      两个 tag（或提交）之间合并的 PR：编号、标题、改了哪些区域
    python3 tools/changelog.py entry <tag>          一次发布的整段记录（内测版短，正式版带要补写的两项）
    python3 tools/changelog.py record <tag> --push  把这段记录追加到那个发布分支的 LOG.md（release-beta / release）
    python3 tools/changelog.py record --main <sha> --push   同上，tag 用这个 main 提交最新的那个 b<N>
    python3 tools/changelog.py rows <从> <到>       docs/releases.md 内测版表格的几行（e2e 从 LOG.md 读）

tag 是 r<N>（语流，flowlang.cn）或 b<N>（内测版，flow.jasa.hk）。每个 tag 指向发布分支上的一个 REQUEST 提交，
REQUEST 第一项是装上去的提交：#60（2026-11-24）以后是构建提交（tag build-<sha12>），它的父提交才是 main 上的那个。
「这次带了哪些 PR」= 上一个同类 tag 的 main 提交到这一个之间的「Merge pull request #N」（标题是合并提交的第二行）。
一个 PR 要是跟着另一个 PR 的分支进了 main（r27 的 #42、#48 跟着 #60），它没有自己的合并提交，这里列不出来：
正式版的记录要对照 GitHub 上那段时间合并的 PR 补上。
自检结果（e2e）只在那个网站的 /api/deploy-status 里，下一次发布就被盖掉，所以 record 在发布刚完成时把它记下来：
内测版由 .github/workflows/beta.yml 每次自动发布后调用；语流由发正式版的人在 deploy.sh 之后调用。

整理过的总账在 docs/releases.md（main）：正式版每次要补「学员能看到的变化」和「用户放行的原话」，这两项只有人写得出来。
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from fnmatch import fnmatch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BJ = datetime.timezone(datetime.timedelta(hours=8))  # 北京时间（没有夏令时）
SITES = {'r': ('release', 'https://flowlang.cn', '语流'), 'b': ('release-beta', 'https://flow.jasa.hk', '内测版')}
LOG = 'LOG.md'
SHA = re.compile(r'^[0-9a-f]{40}$')
MERGE = re.compile(r'^Merge pull request #(\d+) from \S+')

# 改动落在哪个区域：按 tools/README.md「Working agreement」里的区域负责人分。从上往下，第一个对上的算数。
AREAS = [
    ('单词', ['flow/vocab_*', 'flow/fill_examples.py', 'flow/core_words.py', 'flow/lexicon_service.py', 'flow/word_links.py',
            'flow/corpus_data/wordbook*', 'flow/corpus_data/dictionary*', 'flow/corpus_data/meaning-fixes.json',
            'flow/corpus_data/irregular*', 'flow/corpus_data/ecdict*', 'flow/WORDBOOKS*', 'flow/public/src/next/30-*',
            'flow/public/src/next/45-confuse.js', 'flow/public/src/next/50-words.js', 'flow/public/src/next/60-review.js',
            'tools/build_*wordbooks.py', 'tools/build_dictionary.py', 'tools/build_ecdict_subset.py',
            'tools/build_irregular.py', 'tools/gen_word_audio.py', 'tools/audit_meanings.py']),
    ('听和说', ['flow/tts_service.py', 'flow/ielts_speaking.py', 'flow/relisten_service.py', 'flow/sounds.py',
             'flow/voice_eval.py', 'flow/shadow_eval.py', 'flow/scenarios.py', 'flow/meeting_*', 'flow/public/src/next/01-audio-offline.js',
             'flow/public/src/next/21-study-listen.js', 'flow/public/src/next/46-*', 'flow/public/src/next/72-sounds.js',
             'flow/public/src/next/40-listen.css', 'flow/public/src/next/97-listen-speak.css']),
    ('今日和计划', ['flow/daily_*', 'flow/progress_service.py', 'flow/growth_*', 'flow/skills_service.py', 'flow/loop_service.py',
               'flow/public/src/next/1[0-2]-*', 'flow/public/src/next/73-report.js', 'flow/public/src/next/97-progress.css',
               'flow/public/src/next/98-daily-line.css']),
    ('开局和考试', ['flow/exam_*', 'flow/placement_*', 'flow/ability_radar.py', 'flow/public/src/next/0[0-9]-*',
               'flow/public/src/next/41-*', 'flow/public/src/next/42-*', 'flow/public/src/next/48-radar.js',
               'flow/public/src/next/86-sprint.css', 'flow/public/src/next/89-radar.css', 'flow/public/src/next/99-boot.js',
               'flow/public/sw.js', 'flow/public/manifest*']),
    ('后台和班级', ['xmc-admin/*', 'flow/flow_admin.py', 'flow/console_*', 'flow/class_service.py', 'flow/privacy_service.py',
               'flow/survey_service.py', 'flow/account_*', 'flow/auth_service.py', 'flow/feedback_service.py',
               'flow/mail_layout.py', 'flow/public/survey*', 'flow/public/src/next/8[1-3]-*',
               'flow/public/src/next/99-privacy.css', 'flow/public/src/next/99-class.css']),
    ('AI', ['flow/ai_*', 'flow/chat_service.py', 'flow/vertex_*', 'flow/search_eval.py', 'flow-gateway/*', 'tools/ai-gateway/*']),
    ('内容', ['flow/corpus_data/*', 'flow/content_*', 'flow/corpus_*', 'flow/easy_reading.py', 'tools/narration_pack.py',
            'tools/corpus_validate.py', 'tools/gen_audio.py', 'tools/push_media.py', 'flow/media.py']),
    ('操作指南', ['flow/public/guide/*', 'flow/user_guide.py', 'tools/build_guide.py', 'tools/guide_shots.py']),
    ('发版和构建', ['tools/deploy.sh', 'tools/flow-pull*', 'tools/flow-autodeploy*', 'tools/build_release.py',
               'tools/build_front.py', 'tools/release*', 'tools/run_tests.py', 'tools/settle_merge.py', 'tools/changelog.py',
               'tools/beta_setup.py', 'tools/migrate/*', 'tools/README.md', '.github/*', 'docs/*', 'RELEASING.md']),
    ('测试', ['tests/*', 'flow/tests/*', 'tools/ui_test.py', 'tools/ui_server.py', 'tools/ui-fixtures/*', 'tools/qa_*',
            'tools/qa-audio/*']),
]
LISTS = {'flow/upgrade.sh', 'tools/release-files.txt'}  # 新文件顺带登记的两份清单，不算一个区域


def git(*args, check=True):
    r = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f'git {" ".join(args)}: {r.stderr.strip()}')
    return r.stdout.strip()


def area_of(path):
    for name, patterns in AREAS:
        if any(fnmatch(path, p) for p in patterns):
            return name
    return '网站其他'


def areas(paths):
    """改到的区域，按 AREAS 的顺序。「测试」和「网站其他」（app.py、next_service.py 这类各功能都要碰的文件）
    只在没改别的时才算。"""
    seen = []
    for p in paths:
        if p in LISTS:
            continue
        a = area_of(p)
        if a not in seen:
            seen.append(a)
    order = [n for n, _ in AREAS] + ['网站其他']
    seen.sort(key=order.index)
    for minor in ('网站其他', '测试'):
        if len(seen) > 1 and minor in seen:
            seen.remove(minor)
    return seen


def tag_number(tag):
    m = re.fullmatch(r'([rb])(\d+)', tag)
    if not m:
        raise SystemExit(f'{tag}: 要 r<N> 或 b<N>')
    return m.group(1), int(m.group(2))


def tags(prefix):
    out = git('tag', '-l', f'{prefix}*')
    return sorted((t for t in out.split() if re.fullmatch(prefix + r'\d+', t)), key=lambda t: int(t[1:]))


def release(tag):
    """REQUEST 里写的东西：{tag, when, build, main, e2e}；r1、r2 那种空请求 build/main 为 None。"""
    req = git('show', f'{tag}:REQUEST').splitlines()
    first = req[0].split() if req else []
    build = first[0] if first and SHA.match(first[0]) else None
    subject = git('log', '-1', '--format=%s', tag)
    main = build
    if build and ' = build of ' in subject:
        main = git('rev-parse', f'{build}^')  # 构建提交 = main 上那个提交 + 发版时生成的文件
    when = datetime.datetime.fromtimestamp(int(git('log', '-1', '--format=%ct', tag)), BJ)
    return dict(tag=tag, when=when, build=build, main=main, e2e=' '.join(first[2:]))


def previous(tag):
    """同一类里前一个有提交的 tag（跳过 r1、r2 那种空请求）。"""
    p, n = tag_number(tag)
    for t in reversed([t for t in tags(p) if int(t[1:]) < n]):
        if release(t)['main']:
            return t
    return None


def resolve(ref):
    """tag 换成它装上去的 main 提交；别的当提交名。"""
    if re.fullmatch(r'[rb]\d+', ref):
        return release(ref)['main']
    return git('rev-parse', f'{ref}^{{commit}}')


def prs(a, b):
    """a（不含）到 b 之间合并的 PR，按合并先后：[{num, title, sha, areas}]。a 为 None 时只看 b 本身。"""
    rng = [f'{a}..{b}'] if a else ['-1', b]
    out = git('log', '--merges', '--reverse', '--format=%H%x1f%s%x1f%b%x1e', *rng)
    found, seen = [], set()
    for rec in out.split('\x1e'):
        if not rec.strip():
            continue
        sha, subject, body = (rec.strip('\n').split('\x1f') + ['', ''])[:3]
        m = MERGE.match(subject)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        title = next((ln.strip() for ln in body.splitlines() if ln.strip()), subject)
        files = git('diff', '--name-only', f'{sha}^1', sha).splitlines()
        found.append(dict(num=int(m.group(1)), title=title, sha=sha, areas=areas(files)))
    return found


def status(tag, path=None):
    """这个 tag 的自检结果：--status 给的文件，或者那个网站现在的 /api/deploy-status（tag 对得上才算）。"""
    try:
        if path == '-':
            d = json.load(sys.stdin)
        elif path:
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
        else:
            url = os.environ.get('FLOW_STATUS_URL') or SITES[tag[0]][1] + '/api/deploy-status'
            with urllib.request.urlopen(url, timeout=20) as r:
                d = json.load(r)
    except Exception as e:  # 网站没回答：记录照写，只是没有自检结果
        print(f'deploy-status 读不到：{e}', file=sys.stderr)
        return None
    return d if d.get('tag') == tag else None


def checks(d):
    """「DEPLOYED，装了 10 个文件（3 个新的）；轻量 e2e 148/148，服务器报错 0」"""
    if not d:
        return '没取到（发布时 deploy-status 已经是别的 tag，或网站没回答）'
    parts = [d.get('result') or '?']
    m = re.match(r'(\d+) files to install \((\d+) new\)', d.get('files') or '')
    if m:
        parts[0] += f'，装了 {m.group(1)} 个文件（{m.group(2)} 个新的）'
    e = d.get('e2e') or {}
    if d.get('e2e_requested') and e:
        n, bad = e.get('checks', 0), e.get('failed', 0)
        kind = '轻量 e2e' if e.get('light') or d.get('e2e_light') else 'e2e'
        s = f'{kind} {n - bad}/{n}'
        if bad:
            # failed_details (#86, from 2026-11-25) carries why: 「who: name: reason」; older releases only have the names
            s += '，没过：' + '；'.join(e.get('failed_details') or e.get('failed_names') or [])
        s += f'，服务器报错 {e.get("server_errors", "?")}'
        if e.get('cleanup_ok') is False:
            s += '，测试数据没清干净'
        parts.append(s)
    elif not d.get('e2e_requested'):
        parts.append('没跑 e2e')
    return '；'.join(parts)


def same_build(tag):
    """装同一个构建的另一类 tag（语流的 r<N> 对应内测版的哪几个 b<N>）。"""
    rel = release(tag)
    other = 'b' if tag[0] == 'r' else 'r'
    return [t for t in tags(other) if release(t)['build'] == rel['build']] if rel['build'] else []


def pr_lines(items):
    if not items:
        return ['  - 没有新合并的 PR（同一个构建重发，或只是重跑自检）']
    return [f'  - #{p["num"]} {p["title"]}' + (f'（{"、".join(p["areas"])}）' if p['areas'] else '') for p in items]


def entry(tag, d=None):
    rel = release(tag)
    prev = previous(tag)
    when = rel['when'].strftime('%Y-%m-%d %H:%M')
    if not rel['main']:
        return f'### {tag} · {when}\n- 空请求（测试发布通道），没有装任何东西\n'
    items = prs(release(prev)['main'] if prev else None, rel['main'])
    built = f'，构建 `{rel["build"][:7]}`' if rel['build'] != rel['main'] else ''
    lines = [f'### {tag} · {when}', f'- main `{rel["main"][:7]}`{built}']
    lines.append(f'- 新合并的 PR（自 {prev} 起）：' if prev else '- 合并的 PR：')
    lines += pr_lines(items)
    lines.append(f'- 自检：{checks(d)}')
    run = os.environ.get('GITHUB_RUN_ID')
    if run and os.environ.get('GITHUB_REPOSITORY'):
        lines.append(f'- 发布：GitHub Actions，{os.environ.get("GITHUB_SERVER_URL", "https://github.com")}/'
                     f'{os.environ["GITHUB_REPOSITORY"]}/actions/runs/{run}')
    if tag[0] == 'r':
        betas = same_build(tag)
        lines += [f'- 内测版上同一个构建：{"、".join(betas) if betas else "（没有：--skip-beta）"}',
                  '- 学员能看到的变化：（待补，一两句大白话，不写 tag 和技术词）',
                  '- 用户放行的原话：「（待补）」',
                  '- 出过的问题和处理：（没有就写「没有」）']
    return '\n'.join(lines) + '\n'


def logged_checks(branch):
    """LOG.md 里每个 tag 的「自检」那一行，给 rows 用。"""
    text = git('show', f'origin/{branch}:{LOG}', check=False)
    out, cur = {}, None
    for ln in text.splitlines():
        m = re.match(r'### ([rb]\d+) ', ln)
        if m:
            cur = m.group(1)
        elif cur and ln.startswith('- 自检：'):
            out[cur] = ln[len('- 自检：'):]
    return out


def rows(a, b):
    """docs/releases.md 内测版表格：| tag | 时间 | main | 新合并的 PR | 自检 |，新的在上面（和那张表一样）。"""
    p, lo = tag_number(a)
    _, hi = tag_number(b)
    git('fetch', '-q', 'origin', SITES[p][0], check=False)
    done = logged_checks(SITES[p][0])
    out = []
    for t in tags(p):
        if not lo <= int(t[1:]) <= hi:
            continue
        rel, prev = release(t), previous(t)
        if not rel['main']:
            continue
        nums = ' '.join(f'#{n}' for n in sorted(x['num'] for x in prs(release(prev)['main'] if prev else None, rel['main']))) or '—'
        e2e = re.sub(r'^[A-Z_]+[^；]*；', '', done.get(t, '（没记）'))
        out.append(f'| {t} | {rel["when"].strftime("%m-%d %H:%M")} | `{rel["main"][:7]}` | {nums} | {e2e} |')
    return '\n'.join(reversed(out))


def record(tag, d, push):
    branch = SITES[tag[0]][0]
    text_entry = entry(tag, d)
    git('fetch', '-q', 'origin', branch)
    wt = tempfile.mkdtemp(prefix='flow-log-')
    git('worktree', 'add', '-q', '--detach', wt, f'origin/{branch}')
    try:
        for _ in range(3):
            path = os.path.join(wt, LOG)
            if os.path.exists(path):
                with open(path, encoding='utf-8') as f:
                    old = f.read()
            else:
                old = (f'# {SITES[tag[0]][2]}发布记录（自动追加）\n\n每次发布后由 `tools/changelog.py record` 追加一段：装了哪个提交、'
                       f'新合并的 PR 和改到的区域、发布时的自检结果。\n整理过的总账（正式版带学员能看到的变化和用户的原话）在 main 的 '
                       f'`docs/releases.md`。\n')
            if re.search(rf'^### {tag} ', old, re.M):
                print(f'{tag} 已经记过了（{branch}:{LOG}）')
                return
            with open(path, 'w', encoding='utf-8') as f:
                f.write(old.rstrip('\n') + '\n\n' + text_entry)
            subprocess.run(['git', '-C', wt, 'add', LOG], check=True)
            subprocess.run(['git', '-C', wt, 'commit', '-qm', f'log {tag}'], check=True)
            if not push:
                print(subprocess.run(['git', '-C', wt, 'show', '--format=', 'HEAD'], capture_output=True, text=True).stdout)
                print(f'（没推：加 --push 才写进 {branch}）')
                return
            if subprocess.run(['git', '-C', wt, 'push', '-q', 'origin', f'HEAD:refs/heads/{branch}']).returncode == 0:
                print(f'记下了 {tag} → {branch}:{LOG}')
                return
            # 别人刚往这个分支推了（比如又一次发布）：取最新的再追加一次
            subprocess.run(['git', '-C', wt, 'fetch', '-q', 'origin', branch], check=True)
            subprocess.run(['git', '-C', wt, 'reset', '-q', '--hard', f'origin/{branch}'], check=True)
        raise SystemExit(f'推不上 {branch}，{tag} 没记下')
    finally:
        subprocess.run(['git', 'worktree', 'remove', '--force', wt], cwd=ROOT, capture_output=True)


def tag_for_main(sha):
    """这个 main 提交最新的那个 b<N>（beta.yml 在 deploy.sh 之后用）。"""
    sha = git('rev-parse', f'{sha}^{{commit}}')
    found = [t for t in tags('b') if release(t)['main'] == sha]
    return found[-1] if found else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('draft', help='两个 tag 或提交之间合并的 PR')
    s.add_argument('a'); s.add_argument('b')
    s = sub.add_parser('entry', help='一次发布的整段记录')
    s.add_argument('tag'); s.add_argument('--status', help='deploy-status 的 JSON 文件（- 是标准输入）；不给就问网站')
    s = sub.add_parser('record', help='把记录追加到发布分支的 LOG.md')
    s.add_argument('tag', nargs='?'); s.add_argument('--main', help='用这个 main 提交最新的 b<N>')
    s.add_argument('--status'); s.add_argument('--push', action='store_true')
    s = sub.add_parser('rows', help='docs/releases.md 内测版表格的几行')
    s.add_argument('a'); s.add_argument('b')
    args = ap.parse_args(argv)
    git('fetch', '-q', '--tags', 'origin', check=False)
    if args.cmd == 'draft':
        a, b = resolve(args.a), resolve(args.b)
        print('\n'.join(pr_lines(prs(a, b))))
    elif args.cmd == 'entry':
        print(entry(args.tag, status(args.tag, args.status)))
    elif args.cmd == 'record':
        tag = args.tag or (tag_for_main(args.main) if args.main else None)
        if not tag:
            print(f'{args.main or "?"} 还没有发布过（没有 b<N>）：没什么可记的')
            return 0
        record(tag, status(tag, args.status), args.push)
    elif args.cmd == 'rows':
        print(rows(args.a, args.b))
    return 0


if __name__ == '__main__':
    sys.exit(main())
