# Changelog

## 0.1.1 — 2026-09-30

- Package the synthetic offline demo so an installed wheel needs no example checkout.
- Add an explicit `demo` command with a findings preview and retained private reports.
- Keep ordinary audit status/exit-code semantics separate from demo self-check success.
- Add a one-minute walkthrough and a minimal, privacy-conscious external tester task.

## 0.1.0 — 2026-09-27

First public beta.

- Standalone `baseline`, `compare` and `check` commands plus a native Hermes CLI adapter.
- Read-only Git-object comparisons mapped to exact selected Markdown lines.
- Literal argparse command/option and tool-schema structural extraction.
- Referenced source/document path changes with bounded evidence excerpts.
- Private, exclusive snapshot/report writes and explicit partial/unavailable statuses.
- No target imports, skill execution, telemetry, model calls or automatic edits.

Known limits: dynamic interfaces, runtime behavior and prose-only intent are not covered;
all findings need human review. See README and the validation record before use.
