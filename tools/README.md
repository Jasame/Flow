# Tools: deploy and test

## Deploy (push-to-deploy)

```bash
tools/deploy.sh              # deploy HEAD, then the end-to-end test on the server (real AI, ~20 calls)
tools/deploy.sh --no-e2e     # deploy only
tools/deploy.sh <commit>     # deploy a commit that is already on GitHub
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
