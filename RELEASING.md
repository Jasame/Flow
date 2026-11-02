# Flow 3.4 upgrade release

Requires Python 3.11 (standard library only), Git, and Node 22 for frontend regression checks.
From a clean checkout of the release commit:

```bash
python3 tools/release.py check
python3 -m unittest discover -s tests -v
(cd flow && python3 -m unittest discover -s tests -v)
(cd flow-gateway && python3 -m unittest discover -s tests -v)
(cd flow && for test in tests/ui_*.cjs; do node "$test" || exit; done)
```

The output is `dist/Flow-v3.4-Learning-Reliability-Upgrade.zip` and its SHA-256 sidecar.
`validate --output PATH` validates an existing ZIP against this checkout, without rebuilding it.
The builder uses the reviewed `tools/release-files.txt` allowlist, sorted entries, fixed
1980 timestamps and Unix permissions, and uncompressed ZIP entries to avoid differences
between compression library versions. The same commit and identical allowlisted bytes
produce identical ZIP bytes. Build from a clean checkout for published provenance.
The embedded `release-manifest.json` records the source commit, versions and every input hash.
A changed allowlisted file changes the ZIP, even if HEAD has not changed.

The archive has `flow/` and `flow-gateway/` directly at its root, alongside documentation,
license and release tooling. It contains both original upgrade scripts, all their explicit
source inputs, test suites, frontend assets and bundled public teaching corpora.
It never collects runtime directories or arbitrary untracked files. Credentials, databases,
recordings, backups, uploads and personal learning records must never be added to the allowlist.
`flow/flow.env.example` is a public configuration template, not a live configuration.

The check verifies exact archive bytes/membership, required upgrade operands and page assets,
extracts into a temporary directory, runs the existing package boot test against the extracted
website, and compiles gateway modules. It does not execute either deployment script.
The automated Tests workflow also runs the full website, gateway and frontend regressions.

For publication, tag the tested commit `v3.4`, attach the ZIP and SHA-256 sidecar to its GitHub
release, and retain test evidence. Use the upgrade commands in START-HERE.md with a fresh empty
extraction directory. The optional gateway is version 2.2; the website is version 3.4.
Database/configuration backups, retention and rollback safeguards remain in the original scripts.

**Package validation is not production readiness.** No production deployment, production
configuration, real Gemini authentication/connectivity, audio understanding, Google latency,
mobile hardware or real learner calibration is certified by this release. Follow the separate
production acceptance steps in START-HERE.md and VALIDATION.md when authorized.
