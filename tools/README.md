# Tools: deploy and test

## Front-end source (`flow/public/src/next/`)

`next.js` and `next.css` are built: edit the parts in `flow/public/src/next/`, then run
`python3 tools/build_front.py` and commit the parts and the two built files together. The parts are joined in
name order, byte for byte (no transform), so the browser still loads one script and one stylesheet.
`build_front.py --check` fails when a built file is out of date; the test suite and `deploy.sh` run it.
See `flow/public/src/next/README.md` for which part holds what.

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
```

`deploy.sh` pushes, computes the manifest hash from git (`release_manifest.py`), writes
`<commit> <manifest> [e2e]` to `REQUEST` on the `release` branch and tags it `r<N>`. On the server,
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
2. **Merge into main.** No approval needed. main is "waiting for release". Merging changes no site.
3. **内测版:** `tools/deploy.sh --beta <main sha>`. The beta's autodeploy installs it and runs `qa_e2e.py` there.
4. **The owner tries flow.jasa.hk.** A problem goes back through 1–3 as a new `b<N>`.
5. **语流, only after the owner says so (「发正式版」):** `tools/deploy.sh <the same sha>`, with the end-to-end
   test. A failed deploy or test rolls back by itself.
6. **Afterwards:** the public changelog, the version in the guide header, the ops log.

Conventions:

- **Who merges:** until #60 (generated files built at release time, sharded CI) is in main, one session (语流 2) merges,
  in order, because the generated files make PRs collide. After that, see the working agreement below.
- **Trying a PR before it merges:** merge main into that PR's branch and beta-deploy the result. Don't build
  one-off combination branches. 语流 still only gets commits from main.
- **Hotfixes take the same path.** The beta's e2e run takes a few minutes. Skip the beta only when the owner says so.
- **Database schema changes** run against the 内测版's data before they reach 语流's.
- **A commit from before the two-site split** has a `tools/flow-pull.sh` without `F=${FLOW_DIR:-`. That script
  would install into 语流. `deploy.sh --beta` and the beta's autodeploy (status `ABORT_OLD_TOOLS`) both refuse it,
  so merge main into such a branch before beta-deploying it.

### Working agreement (from 2026-11-24)

The owner approved these on 2026-11-24 (「按你的建议改，b6 发完就写进去」). Rules 1 and 2 start once #60 is in main.

1. **Authors merge their own PRs.** When CI is green and the PR merges cleanly into main, the session that wrote it
   turns on auto-merge. The release session (语流 2) handles releases and the servers. 语流 still gets a release only
   when the owner says 「发正式版」.
2. **The 内测版 follows main.** Every merge to main is deployed to the beta automatically, so the beta always shows
   main and there are no hand-numbered batches. Until that is built (语流 15, after #60), run `deploy.sh --beta` by hand.
3. **Small steps.** A change goes to 语流 once the owner has tried it on the beta, or with the weekly release, whichever
   comes first. Never "wait until all of version X is done". Unfinished work merges behind a switch that is off on 语流.
4. **One owner per area.** One long-lived session owns each area: 今日和计划, 开局和考试, 单词, 听和说, 内容, 后台和班级,
   AI, 发版, and CI/build tooling. 总控 coordinates. Only the area's owner changes it at a time. A one-off session is
   archived once its PR is in main.
5. **Habits.**
   - Before pushing, run only the test groups the change touches; CI runs everything.
   - Tests compute counts from the data. Never hard-code how many questions, columns or items there are.
   - A change to an API response shape updates `tools/qa_e2e.py` in the same PR (b5's e2e broke on exactly this).
   - Progress goes into the area's shared note, so other sessions read it instead of waiting for relayed messages.

## End-to-end test on the server (`qa_e2e.py`)

Four internal test learners (ids from 990001, sessions written straight into the database, no password, no
email so no mail can go out) use the live app at the same time with the real AI and synthesized speech
(`qa-audio/`, made by `qa_clips.py`). It checks API behaviour, limits, isolation between learners and
database invariants, then deletes every row the test accounts created and verifies none is left.

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
missing or unused screenshot, a PDF older than the text, or a guide file missing from `release-files.txt`.

When a change adds, renames or removes a page, button or flow:

1. Edit `flow/public/guide/guide.md`. Every page needs a `[去看看](#/page)` line in the chapter that explains it.
2. If what a page looks like changed, run `python3 tools/guide_shots.py [name …]` (local UI server, simulated AI).
3. Run `python3 tools/build_guide.py`, which rebuilds `flow-guide.pdf` and `manifest.json`.
4. Add any new screenshot to `tools/release-files.txt` and commit the guide in the same change.

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
