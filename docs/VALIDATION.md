# Release validation — 27 September 2026

Version 0.1.0 · early beta · supported standalone platforms: macOS and Linux.

## What was checked locally

53 automated tests passed on macOS / Python 3.11.15. Ruff check and formatting passed.
The wheel and source distribution built and passed Twine metadata validation. A separate
environment installed only the wheel with the index disabled, outside the source checkout.

The fresh-wheel acceptance checks exercise compare, baseline, check, exit codes,
missing baselines, overwrite refusal, unchanged skill/snapshot hashes, and loading the
installed Hermes plugin entry point. These checks are repeatable with
scripts/verify_wheel.py after building the package.

A real isolated Hermes 0.21.2 source installation at commit
b6b53c69a6ed49cb099cf1bfe76b5e6edd718e5a successfully loaded the installed plugin
through native discovery. The actual hermes skill-drift command executed help, compare,
baseline, check, and missing-baseline refusal with the expected exit codes.
scripts/verify_native.py creates a temporary home/profile and removes inherited
credentials from the child environment. No live Hermes profile is used.

## Synthetic controls

Ten synthetic demo skills cover removed and newly added CLI options, tool-schema
changes, removed/referenced files, and deliberately unaffected controls.
The report has six findings across five files; five controls are unmarked. The scanned
source raises if executed, but the audit succeeds. This is a constructed acceptance
fixture, not a measured real-world accuracy rate. Follow docs/TRY_IT.md to reproduce it.

## Real bundled-skill corpus

The comparison holds the old skills constant, as a user's skills would be after a
Hermes source update. It compares these public source commits:

- Before: b6b53c69a6ed49cb099cf1bfe76b5e6edd718e5a (12 September).
- After: 41755854adfd96e2871badefdec7993f62324481 (27 September).
- Input: all 262 Markdown files from the before revision's bundled skills directory,
  including reference documents. This is not 262 independent users or 262 SKILL.md files.
- Source coverage: 784 / 938 Python files; 734 / 786 recognized capability keys.
- Result: partial; 121 review hints across 25 Markdown files, with 637 coverage warnings.
- Breakdown: 58 changed referenced paths, 54 newly available options, seven schemas that
  became not-comparable, and two structurally changed tool schemas.
- Measured standalone execution: approximately 11 seconds on the local test Mac.
Runtime depends on source size and hardware.

The complete corpus also passed through the real native Hermes CLI: compare and snapshot
check returned partial/exit 2 with the same 121 findings; all selected input hashes and
the saved snapshot hash remained unchanged. Missing-baseline refusal returned exit 2.

These hints are NOT 121 confirmed bugs. Added options are possible alternatives, changed
paths can be refactors, and dynamic schemas need human review. Warning counts are grouped
in Markdown by limitation type; all source locations remain available in JSON.

Manual triage found a useful defect in our initial extractor: skill_manage was marked as
removed when its schema changed to helper-based construction. The tool declaration
still exists. The release preserves that evidence and reports not_comparable, backed by
a regression test. It never interprets an unknown schema as an absent runtime tool.

An earlier targeted test against the real commits
472d75193f295e509e9f25e962c59655fb26998a and
5ef0b8acb0fa3b0bb9d65ae04313b9b64970d7fd found removal of the literal
hermes model --manual-paste option at line 4 of the synthetic public-source example.
That proof combines a real source change with a deliberately written skill; it does not
establish broad precision or recall.

## Release review and automated gates

Independent review led to regressions for empty capability coverage, changed snapshot
contents, duplicate JSON keys, parser structural keywords, and Unicode display controls.
Missing blobs no longer create fabricated empty-file diffs. Dynamic declarations remain
explicitly unresolved instead of being mislabeled as removals.

The repository's checks workflow runs tests/builds on Linux Python 3.10–3.13 and macOS
Python 3.11, plus native integration on the two pinned Hermes revisions above.
See the [actual workflow runs](https://github.com/mauricemohr88-debug/hermes-skill-drift/actions/workflows/ci.yml)
for hosted execution status; local results are not a substitute for hosted CI.

Publication checks inspect tracked files and distribution archives for private paths and
local review material. Personal reports, baselines and internal review inputs are excluded.
The release workflow checks tag/version agreement, tests, builds, metadata and an offline
fresh-wheel installation before a gated OIDC PyPI upload.

## Remaining boundaries

No runtime execution of scanned skills/source by the scanner. No telemetry, model calls,
skill edits, automatic update hook or automatic baseline advancement. The native Hermes
host necessarily executes its own trusted runtime and this installed plugin.

Dynamic interfaces, plugins outside the inspected source roots, semantic/prose-only
changes and installed dependency behavior remain outside complete coverage.
External user satisfaction, representative precision/recall and willingness to pay
are not measured. A zero-finding result is never runtime compatibility approval.

## Primary evidence

- [User's manual skill audit after an update](https://github.com/NousResearch/hermes-agent/issues/25833#issuecomment-5369259903)
- [Source-first and missing-baseline boundary](https://github.com/NousResearch/hermes-agent/issues/25833#issuecomment-5391841786)
- [Pinned source change](https://github.com/NousResearch/hermes-agent/commit/5ef0b8acb0fa3b0bb9d65ae04313b9b64970d7fd)
- [Dynamic skill_manage declaration](https://github.com/NousResearch/hermes-agent/blob/41755854adfd96e2871badefdec7993f62324481/tools/skill_manager_tool.py)
