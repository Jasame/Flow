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
   After each release the run appends it to `LOG.md` on `release-beta` (`tools/changelog.py record`: the commit, the PRs
   merged since the last one and the areas they touch, the e2e result while deploy-status still shows it). A 内测版
   released by hand is logged with `python3 tools/changelog.py record b<N> --push`.
4. **The owner tries flow.jasa.hk.** Pause first, so the version being tried stays there while other PRs merge:
   `gh variable set BETA_AUTO --body off -R Jasame/Flow`; afterwards `gh variable delete BETA_AUTO -R Jasame/Flow`
   (the next green main goes out). A problem goes back through 1–3.
5. **语流, only after the owner says so (「发正式版」; since 2026-11-25 once a night at 21:00, see the working agreement, 6.):** `tools/deploy.sh <the main sha on the 内测版>`, with the
   end-to-end test. It installs the build the 内测版 got, byte for byte, and refuses a commit that never went to the
   内测版. Check the 内测版's run first (Actions → Beta release, or `e2e` in its deploy-status): a failure there is
   either the AI's (rerun it) or a reason not to release. A failed deploy or test on 语流 rolls back by itself.
6. **Afterwards:** the ledger, the public changelog, the version in the guide header, the ops log. The ledger is
   [`docs/releases.md`](../docs/releases.md) (every release, both sites; server and settings changes in
   [`docs/server-changes.md`](../docs/server-changes.md)). Right after `deploy.sh`:
   `python3 tools/changelog.py record r<N> --push` (keeps the e2e result in `LOG.md` on `release`), then
   `python3 tools/changelog.py entry r<N>` prints the entry: put it at the top of 正式版, write what learners see in one
   or two plain sentences and the owner's words that let it go out, add the 内测版 rows (`changelog.py rows b<from> b<to>`),
   and merge that as a docs-only PR. A server or settings change gets its own entry in `docs/server-changes.md`.

Conventions:

- **Who merges:** the author of the PR, once CI is green and it merges cleanly (see the working agreement below).
  Before #60 (generated files built at release time, sharded CI) one session merged in order, because the generated
  files made PRs collide.
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

### Working agreement (from 2026-11-24)

The owner approved these on 2026-11-24 (「按你的建议改，b6 发完就写进去」). They apply from #60 (in main since 2026-11-24).

1. **Authors merge their own PRs.** When CI is green and the PR merges cleanly into main, the session that wrote it
   turns on auto-merge. The release session (语流 2) handles releases and the servers. 语流 still gets a release only
   when the owner says 「发正式版」. **GitHub as a whole** (the order PRs land in, conflicts, branch cleanup) belongs to the
   ledger session (语流·总账; the owner's choice, 2026-11-25). When a PR is stuck on a conflict or a flaky check, that
   session merges main into its branch and pushes (never with force), then tells the author to pull. It also deletes
   remote branches that are already in main, after noting each name and sha in the shared note `ledger.md`.
   - The session may turn auto-merge on itself with `gh pr merge <number> --repo Jasame/Flow --auto --merge` (the owner
     allowed it on 2026-11-25, 「允许」, knowing that the app's button asks the owner first and the command does not).
     Only its own PRs; never a draft or a PR marked 「先别合」; and it leaves a one-line note on the PR that it turned
     auto-merge on. It does not ask another session to do it for it.
   - **Sensitive PRs ask first** (the owner, 2026-11-25 11:15: 「全绿自动合，敏感的问我」). Everything else goes on
     auto-merge once its tests are green. A PR that changes CI or the GitHub workflows (`.github/`), a deploy script
     (`tools/deploy.sh`, `flow-pull.sh`, `flow-autodeploy.py`, `build_release.py`), server configuration, or keys and
     signing waits until the owner has said yes in the author's session.
2. **The 内测版 follows main.** Every merge to main that passes CI goes to the beta by itself
   (`.github/workflows/beta.yml`, GitHub Actions, the owner's choice; #66), with the light end-to-end test, so the beta
   always shows main and nobody releases it by hand. To keep a version there while the owner tries it, pause with
   `gh variable set BETA_AUTO --body off -R Jasame/Flow` (`gh variable delete BETA_AUTO -R Jasame/Flow` resumes).
3. **Small steps.** A change goes to 语流 with the next nightly release (6. below), once it has been on the beta. Never "wait until all of version X is done". Unfinished work merges behind a switch that is off on 语流.
4. **One owner per area.** One long-lived session owns each area: 今日和计划, 开局和考试, 单词, 听和说, 内容, 后台和班级,
   AI, 发版, and CI/build tooling. 总控 coordinates. Only the area's owner changes it at a time. A one-off session is
   archived once its PR is in main.
5. **Habits.**
   - Before pushing, run only the test groups the change touches (see 推之前跑哪些测试 below); CI runs everything.
   - Tests compute counts from the data. Never hard-code how many questions, columns or items there are.
   - A change to an API response shape updates `tools/qa_e2e.py` in the same PR (b5's e2e broke on exactly this).
   - Progress goes into the area's shared note, so other sessions read it instead of waiting for relayed messages.
6. **语流 once a night** (the owner, 2026-11-25 11:15: 「每天固定一次，一次点头」). 语流 is released once a day at 21:00,
   and not at all when nothing new is on the beta. At 20:00 the release session (语流 2) gives the owner the list of
   what goes out, the known problems and the full text of the jasa.hk changelog. One 「发」 from the owner releases 语流
   and publishes the changelog together. Afterwards the ledger entry, as in 发布顺序 step 6.
7. **App test builds** (the owner: 「自动打包，发给同学前问我」). iOS, Android and desktop builds are made automatically
   once their change is in main. Sending one to trial students, to TestFlight external testing or to an app store
   needs the owner's yes first.
8. **Reports.** 总控 (语流 1) gives the owner a summary about every two hours.
9. **Automation stays silent** (the owner, 2026-11-25: 「后台运行的应用不要播放系统声音」). Sessions work on the owner's
   Mac, so nothing they run in the background may make a sound:
   - browser automation is muted: every tool that starts a browser calls `silent(pw)` from `tools/quiet.py` right
     after `with sync_playwright()` (`tests/test_ci.py` checks). Chrome starts with `--mute-audio`, and every page gets
     a script first: media at volume 0 once it plays, Web Audio through a gain of 0, the browser voice at volume 0 (on a
     Mac that voice is the system's speech, which `--mute-audio` does not reach). `.muted` is left to the app. Playback
     still runs (play, currentTime, ended, the voice's events), so tests of sound keep checking it, unheard;
   - simulator automation mutes on the web side the same way (`tools/ios_sim_check.py`);
   - no `say`, `afplay` or `osascript` beep;
   - no Escape key press when there is nothing to cancel (macOS beeps);
   - a test that has to be heard is asked for first.

## 推之前跑哪些测试 (what to run before pushing)

CI runs everything on every pull request, split into shares that run at the same time (`tools/run_tests.py`: 2
website shares and 5 UI shares, about 6 minutes in all, where one job each took 25). So before pushing, run only what
the change touches; don't run the whole suite locally as well. Two rules keep main moving when many PRs are open
(2026-11-25): a run on main is never cancelled by the next merge (only a PR's older run is): the run in progress
finishes, and of the merges waiting behind it the newest runs next, so main's newest commit always reaches the 内测版; and a PR that touches nothing the UI tests depend on (`UI_INPUTS` in `run_tests.py`:
not `flow/`, not the UI tools) skips the 5 UI shares, taking 3 of the account's 20 runners instead of 8.

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

## MSI 测试机 (the owner's PC as a test machine)

The owner's MSI (i7-12700, WSL2 Ubuntu 24.04 with 16 processors) runs Tests' heavy jobs — the 2 website shares and
the 5 UI shares — as self-hosted runners `msi-1` … `msi-6`, all labelled `msi`, so they are off GitHub's 20-job limit.
Everything else (`changes`, the gates `backend` / `ui`, `frontend`, the watch, every release and the monitor) stays on
GitHub's machines.

- **Set up** (in WSL, once; safe to run again): `git clone https://github.com/Jasame/Flow.git ~/Flow && cd ~/Flow &&
  bash tools/msi-setup.sh`. It installs Python 3.11, Google Chrome, the Chinese fonts and Playwright, unpacks 6
  sha256-checked runner folders with a clean-up hook, runs a self-check (front end, guide PDF, two test files, one UI
  share), then prints the commands that register the runners: the owner types the token from the GitHub page there;
  the script never sees it. `msi-setup-check.yml` runs the whole script on a GitHub machine whenever it changes.
- **Proxy** (the MSI is in mainland China): v2rayN's system proxy on Windows listens on this machine (e.g.
  `http://127.0.0.1:10808`), and `.wslconfig` (`networkingMode=mirrored`, `autoProxy=true`, `dnsTunneling=true`) hands
  it to a WSL shell as `https_proxy`. With it, `msi-setup.sh` first checks it can reach github.com (if not: 「先开
  v2rayN 的系统代理」), then gives it to what does not read the shell's: apt (`/etc/apt/apt.conf.d/95flow-proxy`), the
  commands it runs with sudo, and every runner's `.env` (`https_proxy`, `http_proxy`, `no_proxy=localhost,127.0.0.1,
  ::1,100.64.0.0/10`; a runner is a systemd service), restarting a runner whose `.env` changed. Without a proxy none of
  this is written. A new port: run the script again in a shell that has it. Only a local address is ever written; the
  node link stays in v2rayN. `msi-setup-check.yml` runs the script through a local squid too.
- **How a run picks** (`tools/ci_runner.py pick`, in `changes`): the MSI only if the repository variable `MSI_RUNNER`
  is `on`, the run is main's or a pull request from this repository (never a fork's), fewer than 6 MSI jobs are queued
  or running, and a probe (`msi-probe.yml`) starts on it within 45 s. Otherwise GitHub's machines, exactly as before.
  GitHub never moves a queued job, hence the probe; if the MSI goes away right after answering, `msi-watch` cancels the
  run after 10 minutes without a machine (for main it also starts a new run, which then uses GitHub's machines).
- **Why 6 runners:** a website share keeps 4 processors busy, a UI share about 2; a run's 7 shares then start 6 at once
  (2×4 + 4×2 = 16) and the 7th when a website share ends. More would squeeze the UI tests' timing.
- **Turn it on** (after the runners show Idle under Settings → Actions → Runners): `gh variable set MSI_RUNNER --body on
  -R Jasame/Flow`. **Pause** (every run from the next one on uses GitHub's machines): `gh variable set MSI_RUNNER
  --body off -R Jasame/Flow`. A switched-off or sleeping PC needs nothing: the probe gets no answer and runs go to
  GitHub's machines by themselves.
- **Stop the runners** (in WSL): `for i in $(seq 1 6); do (cd ~/actions-runner/msi-$i && sudo ./svc.sh stop); done`, or
  `wsl --shutdown` in Windows. **Remove them**: `sudo ./svc.sh uninstall` in each folder, then delete them under
  Settings → Actions → Runners (or `./config.sh remove --token <the page's removal token>`).
- **Safety:** no workflow passes a secret to the MSI; its jobs get the run's read-only token (`contents: read`). The
  runners run as the owner's Linux user (no sudo without a password). Each job keeps its temporary files in its
  runner's `_temp` (`TMPDIR`), which the runner clears, and a hook (`ACTIONS_RUNNER_HOOK_JOB_COMPLETED`) empties the
  workspace after every job. A fork's pull request is never sent there by the pick, and because a fork could edit the
  workflow itself, Settings → Actions → General keeps "Require approval for all outside collaborators": never approve a
  fork's run that changes `.github/workflows/` without reading it.

## End-to-end test on the server (`qa_e2e.py`)

Four internal test learners (ids from 990001, sessions written straight into the database, no password, no
email so no mail can go out) use the live app at the same time with the real AI and synthesized speech
(`qa-audio/`, made by `qa_clips.py`). It checks API behaviour, limits, isolation between learners and
database invariants, then deletes every row the test accounts created and verifies none is left.

**Light run** (`QA_LIGHT=1`, REQUEST `e2e light`, `deploy.sh --beta --light`): skips the checks that send a recording
to the AI (pronunciation and the sound card, shadowing, a dialogue turn by voice, which becomes a typed one, and a
spoken retell) and notes each skip. **At most `QA_AI_SLOTS` (default 1) AI requests** of a run are in flight at once,
so a test never takes all of a model's places from learners. `report.json` and `/api/deploy-status` record both
(`e2e.light`, `e2e_light`). Each failed check comes with a reason in `e2e.failed_details`: only the error text the app
answered with (and an AI job's kind), an HTTP status or an exception's type, never what anyone wrote; so a release's
Actions log says why without a look at the server. A light run checks 143 things, a full one 150 (against the local UI server, 2026-11-24).

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

## The iPhone checklist in the iOS Simulator (`ios_sim_check.py`)

```bash
python3 tools/ios_sim_check.py <out dir> [--only shell,keyboard,audio,mic,update] [--udid UDID] [--safari]
python3 tools/ios_sim_check.py <out dir> --host localhost:PORT --ui-server <ui_server state dir>[:learner]
```

Runs the home-screen-app part of the iPhone checklist on the simulator's real WebKit (Mac with Xcode): back
buttons, logo and tabs clear of the Dynamic Island and the home bar, the status-bar strip in light and dark,
landscape, the real on-screen keyboard (judged from the screenshot: iOS 26+ moves the web view without telling the
page), word sound in 连续 and 标准 with the time from tap to sound, the lock-screen title, the microphone sheet and
the microphone let go after recording, and the new-version line. It talks to the simulator's Web Inspector socket,
so it reaches the home-screen app, which safaridriver cannot. Adding the site to the home screen, turning the device
and the system's microphone 「允许」 are taps (steps at the top of the file). On the beta it stays a guest; pages that
need an account run against `ui_server.py` with `--ui-server`. Results and screenshots: `<out dir>/<device>-report.md`.

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
