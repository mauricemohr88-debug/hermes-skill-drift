# Try it without touching your Hermes

## One command from the installed package

Version 0.1.1 includes the demo in the installed package. Python 3.10+ and Git are
required; PyPI is not required. Start in a folder outside the project checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install "git+https://github.com/mauricemohr88-debug/hermes-skill-drift.git@v0.1.1"
source .venv/bin/activate
hermes-skill-drift demo
```

No real Hermes install or private skill is needed. The command prints a preview and
the exact directory containing `baseline.json`, `report.md` and `report.json`.
It retains those files so you can inspect the evidence. It does not download anything
or execute the generated source/skill instructions. It creates two commits only inside
its own new synthetic repository, with hooks and signing disabled.

Optional: `hermes-skill-drift demo --directory ./my-drift-demo`. Choose a new path;
existing paths are refused. Do not use a symlink path; on macOS prefer a normal project
folder or `/private/tmp/`, not `/tmp/`.

### One-minute tour

1. Run the demo. The old example skill still mentions `hermes model --legacy`.
2. Look at the preview: the new synthetic source no longer declares `--legacy` and
   declares `--refresh`. The scanner points to the skill line and source evidence.
   It does **not** claim those options are equivalent or rewrite the skill.
3. Open `report.md`: six hints affect five skills; the other five examples are controls.
   File references and a tool-schema change are also visible.
4. Note the boundary: `needs_review` means a person should inspect the hint. The demo
   returns 0 for its expected constructed outcome, not because the skills are approved.
   Ordinary `compare`/`check` still return 1 for these findings.

## Small external test: your own source checkout

The most useful next test is with a Hermes Git/source install and a custom skill that
mentions a command, option, tool name or source-file path. Both before/after commits
must already be available locally. ZIP-only installs are not covered by this test.
Use one deliberately selected Markdown file first:

```sh
hermes-skill-drift compare --repo /path/to/hermes-agent \
  --before OLD_COMMIT --after NEW_COMMIT --skills /path/to/selected/SKILL.md
```

Five-minute feedback task (not a promise of runtime):

- Did installation work, and what package/Python/Git versions did you use?
- Which line did you expect to need review, and what did the report actually say?
- Was the hint actionable, irrelevant, or missing? Include one minimal redacted excerpt.
- Were the warning/status and the distinction from runtime compatibility understandable?
- What was the first step you could not complete without help?

No private configs, credentials or complete baselines are needed. Reports can contain
private excerpts/paths; redact them before sharing. No external tester success or
accuracy rate is inferred from the demo.

## Optional source-checkout example

The example creates a new disposable source repository and ten synthetic Markdown skills.
Only that demo repository receives two commits; your project work and live Hermes remain
unchanged. No selected skill or source instructions are executed during the audit.

From the project directory, after installing the package:

```sh
python examples/create_demo.py ./my-drift-demo
hermes-skill-drift baseline --repo ./my-drift-demo/source --ref before \
  --skills ./my-drift-demo/skills --output ./my-drift-demo/baseline.json
hermes-skill-drift check --repo ./my-drift-demo/source --after after \
  --baseline ./my-drift-demo/baseline.json --skills ./my-drift-demo/skills \
  --output ./my-drift-demo/report.md
```

Expected: exit 1 (`needs_review`), findings on the first five skill files, no mapped
findings on the five controls. The report identifies the removed `--legacy` option,
new `--refresh` option, changed tool schema, removed path and changed guide.
The scanner does not claim that `--refresh` replaces `--legacy`.
These are deliberately constructed cases, not a measured real-world accuracy rate.

To show the failure boundary, use a non-existent baseline filename: exit 2,
`baseline_unavailable`, never a clean result. Re-running with the same output path
is refused to preserve your previous baseline/report. Pick a new output filename.

Before sharing a real report, redact private skill excerpts and absolute filesystem paths.
Do not upload the baseline: it contains the selected Markdown text.
