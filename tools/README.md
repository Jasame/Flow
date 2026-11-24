# Tools: deploy and test

## Front-end source (`flow/public/src/next/`)

`next.js` and `next.css` are built: edit the parts in `flow/public/src/next/`, then run
`python3 tools/build_front.py` to see the change locally. **Commit only the parts**: git ignores the two built files
(since 2026-11-24), and a release builds them from the commit (`tools/build_release.py`, below). The parts are joined
in name order, byte for byte (no transform), so the browser still loads one script and one stylesheet.
`build_front.py --check` fails when a built file is out of date with its parts; the tests and every release build run it.
See `flow/public/src/next/README.md` for which part holds what.

**Files a release builds** (`tools/build_release.py`): `next.js`, `next.css`, the guide's `flow-guide.pdf` and its
`manifest.json`. They are listed in `release-files.txt` like every installed file, but never committed, so pull
requests can no longer conflict over them. `python3 tools/build_release.py --here` builds all four in a checkout (the
PDF only when `guide.md` or a screenshot changed; it needs Playwright, which drives the installed Chrome);
`tools/run_tests.py` and `tools/ui_server.py` build the front end themselves.

`flow/corpus_data/dictionary-flow.json` is built too: after changing `yl-reference.json`, `ecdict-flow.json`,
`meaning-fixes.json` or `irregular-flow.json`, run `python3 tools/build_dictionary.py` (tests and `deploy.sh` check it).
The app loads this compact file instead of parsing ~38 MB of source JSON, which kept the server process ~100 MB larger.
`flow/corpus_data/wordbooks-open.json` (中考, 高考, NAWL, BSL word books) is built by `tools/build_open_wordbooks.py`
from downloaded ECDICT and NGSL Project files; `flow/WORDBOOKS-OPEN.md` has the sources, licences and commands.

`flow/corpus_data/wordbooks.json` (the 专四 / 专八 word books) is built by `python3 tools/build_wordbooks.py` from the
frequency list, the ECDICT subset and the dictionary's word list; `--check` fails when it is out of date (the tests run it).
The selection rule, its sources and sizes are in `flow/WORDBOOKS.md`.

## Deploy (push-to-deploy)

```bash
tools/deploy.sh              # deploy HEAD, then the end-to-end test on the server (real AI, ~20 calls)
tools/deploy.sh --no-e2e     # deploy only
tools/deploy.sh <commit>     # deploy a commit that is already on GitHub
tools/deploy.sh --beta <commit>   # the same for the 内测版 (flow.jasa.hk); see 发布顺序 below
tools/deploy.sh --skip-beta <commit>  # 语流 without the 内测版 first: only when the owner says so
```

`deploy.sh` pushes, then gets the commit's **release build**: `deploy.sh --beta` runs `build_release.py <commit>`, which
builds the files a release builds in a temporary worktree of that commit, checks them the way the tests did while they
were committed (`build_front.py --check`, `test_guide.py` on the PDF and its manifest, `node --check`), commits them on
top of the commit and pushes that as tag `build-<sha12>`. `deploy.sh <commit>` for 语流 reuses that same build commit
(`--reuse`) and refuses one that was never requested on the 内测版, so both sites install the same bytes. A commit from
before 2026-11-24 still has those files in git and is released as it is. Then `deploy.sh` computes the build commit's
manifest hash from git (`release_manifest.py`), writes `<build commit> <manifest> [e2e]` to `REQUEST` on the `release`
branch and tags it `r<N>`. The server needs nothing new: it deploys the build commit like any commit. The release
machine needs Python 3.11 with Playwright for the PDF (`FLOW_PLAYWRIGHT_PYTHON` names one); the 内测版 release
takes about a minute longer for it. On the server,
`flow-autodeploy.timer` runs `flow-autodeploy.py` every minute: it asks jsDelivr for the next tag only
(the server cannot reach GitHub; a new tag is never cached, branch heads are), takes `flow-pull.sh` and the
test from that commit (sha256-checked), deploys (per-file sha256, manifest, backup, health checks, automatic
rollback), runs `qa_e2e.py` when asked, and writes the outcome to `data/deploy-status.json`, served at
`/api/deploy-status`. `deploy.sh` waits for it and exits non-zero if the deploy or the test failed.
Each tag is handled once; to retry, run `deploy.sh` again (new tag).

One-time server setup: `flow-autodeploy.py` in `/root/claude-ops`, the `.service` and `.timer` in
`/etc/systemd/system`, `systemctl enable --now flow-autodeploy.timer`, and the next tag number in
`/root/claude-ops/autodeploy/next`.

## 发布顺序: 内测版 first, then 语流

There are two sites on the Hong Kong server: **语流** (flowlang.cn, the public site; tags `r<N>` on `release`) and
the **内测版** (flow.jasa.hk, its own data, open to anyone with the link; `tools/deploy.sh --beta`, tags `b<N>` on
`release-beta`). The rule is that 语流 only ever gets a commit that ran on the 内测版 first, **the same sha**.
The owner agreed this order on 2026-11-24.

1. **One branch and one PR per change, targeting main.** Don't stack PRs. If one has to sit on another, retarget it
   to main as soon as the one below merges. CI (backend, frontend, ui) must be green.
2. **Merge into main.** No approval needed. main is "waiting for release". Merging changes no site. Green PRs can be
   merged one after another without merging main into each again (the protection rule doesn't require it): the built
   files no longer conflict, and the release lists are sorted, one name per line. A PR that GitHub says conflicts
   merges main, runs `python3 tools/settle_merge.py`, and resolves by hand only what that leaves.
3. **内测版, by itself:** when main's own CI run passes (about 6 minutes after a merge; it tests the PRs together),
   `.github/workflows/beta.yml` runs `tools/deploy.sh --beta <that commit>` on a GitHub runner: it builds next.js,
   next.css and the guide PDF (Noto Sans CJK on the runner), requests `b<N>`, and waits for the 内测版's autodeploy to
   install it and run the **light** `qa_e2e.py` (no recordings sent to the AI, see below). Merges in a row release only
   the newest commit; a failed release or test fails
   the run (Actions → Beta release; GitHub emails it). The 内测版 shows what it runs at https://flow.jasa.hk/api/deploy-status (`tag`, `commit`: the build commit, whose
   parent is the main commit; `result`; `e2e`). Nobody releases the 内测版 by hand any more, unless it is paused (below).
4. **The owner tries flow.jasa.hk.** Pause first, so the version being tried stays there while other PRs merge:
   `gh variable set BETA_AUTO --body off -R Jasame/Flow`; afterwards `gh variable delete BETA_AUTO -R Jasame/Flow`
   (the next green main goes out). A problem goes back through 1–3.
5. **语流, only after the owner says so (「发正式版」):** `tools/deploy.sh <the main sha on the 内测版>`, with the
   end-to-end test. It installs the build the 内测版 got, byte for byte, and refuses a commit that never went to the
   内测版. Check the 内测版's run first (Actions → Beta release, or `e2e` in its deploy-status): a failure there is
   either the AI's (rerun it) or a reason not to release. A failed deploy or test on 语流 rolls back by itself.
6. **Afterwards:** the public changelog, the version in the guide header, the ops log.

Conventions:

- **One session merges and releases.** Others finish and test their PR, then hand it over. Two sessions merging at
  the same time is how stacked merges go wrong.
- **Trying a PR before it merges:** pause the automatic release (`BETA_AUTO` off), merge main into that PR's branch and
  beta-deploy the result by hand (`tools/deploy.sh --beta <branch sha>`). Don't build one-off combination branches.
  语流 still only gets commits from main.
- **Which end-to-end test runs where.** The light one (no recordings to the AI) on every automatic 内测版 release; the
  full one on every 语流 release (`deploy.sh` refuses `--light` there), in the daily run, and on the 内测版 when someone
  asks for it (Run workflow with e2e = full, or `tools/deploy.sh --beta <sha>` without `--light`). Recordings go
  through the Gemini relay, whose two places 语流's learners share: on 2026-11-24 three release tests in half an hour
  made 语流 slow.
- **Hotfixes take the same path.** The beta's e2e run takes a few minutes. Skip the beta only when the owner says so
  (`tools/deploy.sh --skip-beta <sha>`).
- **The pause `BETA_AUTO`** (a repository variable): `off` while the owner is trying a version or a PR branch is on
  the 内测版 for a trial; merges then wait on main. Unset (or anything else), main goes to the 内测版 by itself. A release by
  hand still works either way: `tools/deploy.sh --beta <sha>` on the Mac (it prints the PDF with PingFang there), or
  Actions → Beta release → Run workflow. An e2e failure that is the AI's, not the app's (it happens), is retried with
  Run workflow for the same commit: same build, new `b<N>`.
- **Database schema changes** run against the 内测版's data before they reach 语流's.
- **A commit from before the two-site split** has a `tools/flow-pull.sh` without `F=${FLOW_DIR:-`. That script
  would install into 语流. `deploy.sh --beta` and the beta's autodeploy (status `ABORT_OLD_TOOLS`) both refuse it,
  so merge main into such a branch before beta-deploying it.

## 推之前跑哪些测试 (what to run before pushing)

CI runs everything on every pull request, split into shares that run at the same time (`tools/run_tests.py`: 2
website shares and 5 UI shares, about 6 minutes in all, where one job each took 25). So before pushing, run only what
the change touches; don't run the whole suite locally as well.

| the change touches | run before pushing |
| --- | --- |
| a module in `flow/` | `python3 tools/run_tests.py --changed` (the test files that import what changed, and the changed tests themselves), or name them: `python3 tools/run_tests.py test_vocab test_next` |
| front-end parts (`flow/public/src/next/`) | `python3 tools/run_tests.py --changed`, and the UI groups of the pages changed: `python3 tools/run_tests.py --ui phone desktop` (add `sprint`, `start`, `progress`, `listen-speak`, `swipe`, `backlog`, `wechat`, `about`… for those pages) |
| `guide.md` or a guide screenshot | `python3 tools/run_tests.py test_guide` (a PDF is not needed; the release prints it) |
| `release-files.txt`, `flow/upgrade.sh` | `python3 -m unittest discover -s tests` and `python3 tools/release.py check` (after `python3 tools/build_release.py --here`) |
| `tools/deploy.sh`, `flow-pull.sh`, `flow-autodeploy.py` | `python3 tools/run_tests.py test_channels`, and a full 内测版 release before the PR counts as done |
| unsure, or many areas | `python3 tools/run_tests.py` (all website tests in parallel, about 3 minutes on a laptop) and let CI run the UI |

`--list` prints what would run without running it. A UI group is one switch of `ui_test.py`; `run_tests.py --ui` with
no group runs all five CI shares at once on the laptop (about 6 minutes).

## End-to-end test on the server (`qa_e2e.py`)

Four internal test learners (ids from 990001, sessions written straight into the database, no password, no
email so no mail can go out) use the live app at the same time with the real AI and synthesized speech
(`qa-audio/`, made by `qa_clips.py`). It checks API behaviour, limits, isolation between learners and
database invariants, then deletes every row the test accounts created and verifies none is left.

**Light run** (`QA_LIGHT=1`, REQUEST `e2e light`, `deploy.sh --beta --light`): skips the checks that send a recording
to the AI (pronunciation and the sound card, shadowing, a dialogue turn by voice, which becomes a typed one, and a
spoken retell) and notes each skip. **At most `QA_AI_SLOTS` (default 1) AI requests** of a run are in flight at once,
so a test never takes all of a model's places from learners. `report.json` and `/api/deploy-status` record both
(`e2e.light`, `e2e_light`). A light run checks 143 things, a full one 150 (against the local UI server, 2026-11-24).

## Multi-device UI test (`ui_test.py`)

```bash
pip install playwright        # uses the installed Google Chrome; no browser download
python3 tools/ui_test.py [out dir] [phone|phone-land|tablet|desktop …]
```

Starts its own local server (`ui_server.py`: throwaway database, simulated AI, a signed-in learner per device)
and checks every page on a phone, a phone held sideways, a tablet and a desktop: no sideways scrolling,
nothing hidden under the bottom tabs, touch targets of at least 32 px, and the input paths — keyboard
shortcuts, Enter in answer boxes, swipes in review, closing sheets by key or by dragging, the playback stop
control, step switching and list filters. Screenshots of every page go to the out dir.

## Monitoring

- **Server errors**: anything that reaches a learner as 「服务暂时异常」 is written to the journal (`journalctl -u flow`)
  with its stack trace and kept in `server_errors` (last 500, path only, no query or request body). The admin page
  has an 「错误」 tab that groups them by where in the code they happened (`flow/ops_errors.py`).
- **Live status**: `/api/deploy-status` carries `live` (memory, uptime, threads, server errors in 24 h) next to the
  last release and `daily` (the daily end-to-end test).
- **Daily end-to-end test**: `flow-autodeploy.py` runs `qa_e2e.py` once a day between 04:00 and 05:00 server time
  against what is deployed (~17 AI calls).
- **External check**: `.github/workflows/monitor.yml` checks the site every 15 minutes (pages and APIs answer, fewer
  than 10 errors a day, memory under 350 MB, last release fine, daily test recent and passing). GitHub emails a
  failed run to whoever last changed that schedule. It runs from `main`.

## 操作指南 (user guide)

The guide has one source, `flow/public/guide/guide.md`. The site shows it at `#/guide` and offers it as a PDF.
`flow/tests/test_guide.py` fails when the guide falls behind: a page or a 练习 tile that the guide never links, a
missing or unused screenshot, a PDF older than the text (where a PDF was built), or a guide file missing from `release-files.txt`.

When a change adds, renames or removes a page, button or flow:

1. Edit `flow/public/guide/guide.md`. Every page needs a `[去看看](#/page)` line in the chapter that explains it.
2. If what a page looks like changed, run `python3 tools/guide_shots.py [name …]` (local UI server, simulated AI).
3. Add any new screenshot to `tools/release-files.txt` and commit the guide in the same change.
4. Don't commit a PDF: `flow-guide.pdf` and `manifest.json` are printed from the commit when it is released
   (`tools/build_release.py`, which runs `build_guide.py` and then `test_guide.py` on the result). To look at the PDF
   before that, `python3 tools/build_release.py --here`. The e2e test checks on each site that the PDF downloads.

## Text model vendors (xmc-api, api.xmc.hk)

Flow's text calls can use a cheaper model than the main one. With `FLOW_TEXT_AI_MODEL=flow-text` in
`/etc/flow.env`, they go to the same gateway and key as the main model (api.xmc.hk, the xmc-api gateway) under the
model name `flow-text`. The gateway's console (xmc.hk/api-admin/) decides which vendor answers it: DeepSeek, Qwen,
or Gemini. If `flow-text` fails or is switched off, the main model answers. `tools/ai-gateway/README.md` is the
step-by-step checklist (in Chinese), and `flow/ai_check.py` checks the text model on its own.

## Audio: this server first, Cloudflare R2 as the second line and the master copy

`tools/push_media.py` uploads the audio that `tools/gen_audio.py` and `tools/gen_word_audio.py` write to the R2 bucket
(only new or changed files) and writes `flow/corpus_data/media-manifest.json`. After a release with that manifest, the
server fetches a listed file from R2 the first time someone asks for it (`flow/media.py`, with `FLOW_MEDIA_BASE` set),
so audio is never copied onto the server by hand; the page plays from R2 by itself when this server cannot answer.
`tools/media/README.md` is the set-up checklist (in Chinese): bucket, domain, CORS, the upload token, and switching it on.
