# Try it without touching your Hermes

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
new `--refresh` alternative, changed tool schema, removed path and changed guide.
These are deliberately constructed cases, not a measured real-world accuracy rate.

To show the failure boundary, use a non-existent baseline filename: exit 2,
`baseline_unavailable`, never a clean result. Re-running with the same output path
is refused to preserve your previous baseline/report. Pick a new output filename.

Before sharing a real report, redact private skill excerpts and absolute filesystem paths.
Do not upload the baseline: it contains the selected Markdown text.
