# Hermes Skill Drift Check

**Which parts of my own skills deserve another look after a Hermes update?**

This local, read-only Python tool compares two committed Hermes source versions and
maps supported native interface changes to explicit references in your selected
Markdown skills. You get exact skill lines, commit identities and source evidence.

**Early beta: evidence for human review, not a compatibility guarantee.**
Not affiliated with Nous Research.
No telemetry, model calls, cloud upload, automatic edits or background service.

## Quick start

Requires Python 3.10+ and Git on macOS or Linux. Install a pinned release in an isolated
environment (also works without PyPI):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install "git+https://github.com/mauricemohr88-debug/hermes-skill-drift.git@v0.1.0"
source .venv/bin/activate
hermes-skill-drift --help
```

Before an update, select only the skills you want inspected:

```sh
hermes-skill-drift baseline --repo /path/to/hermes-agent --ref HEAD \
  --skills /path/to/your-selected-skills --output baseline.json
```

After updating Hermes separately:

```sh
hermes-skill-drift check --repo /path/to/hermes-agent --baseline baseline.json \
  --after HEAD --skills /path/to/your-selected-skills --output report.md
```

Already know the two versions? No snapshot required:

```sh
hermes-skill-drift compare --repo /path/to/hermes-agent \
  --before OLD_COMMIT --after NEW_COMMIT --skills /path/to/your-selected-skills \
  --format json --output report.json
```

Repeat `--skills` for more explicitly selected folders/files. Selected directories include
non-hidden `.md` files recursively (including reference documents); other file types are
not read. No automatic discovery of profiles, credentials or your home directory.
Output files must not already exist. Standard output is used when no `--output` is supplied.
Selected input/output paths must not traverse symlinks. On macOS, use `/private/tmp/`
instead of its `/tmp/` alias for temporary skill/output paths.
Snapshots contain selected skill text; keep them private. Reports contain excerpts/paths.

## What it catches — and what it does not

- Removed or structurally changed literal argparse command/option definitions referenced
  by a skill. Added options are suggested for review when the parent command is mentioned.
- Structural changes in literal tool schemas mentioned by exact tool name.
- Removed or changed repository files referred to by relative source path, including docs.
- Skill-content/hash changes since a saved snapshot, with source versions kept separate.

All findings say **review recommended**. A removed source declaration does not establish
that a command fails at runtime: it might have a dynamic registration elsewhere. A skill
may quote an obsolete command intentionally. Source-file moves may be harmless refactors.

This is not a general skill linter, sandbox, security audit or LLM semantic judge. It cannot
infer that arbitrary manual cleanup instructions should become a native backup command
unless an explicit supported reference connects them. Dynamic CLI/schema construction,
external plugins, live dependency behavior, prose-only semantic drift and runtime success
remain outside proven coverage. Coverage warnings are included, not silently discarded.

Only committed objects are inspected. Uncommitted source changes are ignored explicitly.
Both revisions and required blobs must already exist locally; the scanner never fetches.
ZIP-only installations and missing commits produce `baseline_unavailable`, not a green check.
The tool does not assume a Git commit is a trusted release: choose trusted upstream refs.

## Status and exit codes

| Status | Exit | Meaning |
| --- | --- | --- |
| `no_mapped_changes` | 0 | No mapped findings within supported static coverage; not compatibility proof |
| `needs_review` | 1 | Evidence-linked findings need human review |
| `partial` | 2 | Coverage gaps exist; findings can still be useful |
| `baseline_unavailable` | 2 | Required input/evidence unavailable or invalid; audit not completed |

Changed skill contents since a snapshot produce `partial`: findings use current text only,
and the old instructions have not thereby been reviewed.

`baseline` success returns 0. A baseline is a snapshot, **never approval or a completed
skill review**. Reports always have `reviewed: false`; comparisons never advance the baseline.

## Optional Hermes CLI integration

The wheel exposes the native `hermes_agent.plugins` entry point. Once deliberately installed
in Hermes's own Python environment and enabled through Hermes's plugin controls, it registers:

```sh
hermes skill-drift compare --repo /path/to/hermes-agent \
  --before OLD_COMMIT --after NEW_COMMIT --skills /path/to/selected-skills
```

For a source install, install this package using the Python belonging to your Hermes
environment, then run `hermes plugins enable skill-drift` and
`hermes skill-drift --help`. Installing into an unrelated pipx/venv environment provides
the standalone command only; Hermes cannot discover that environment's entry points.

There is no model-callable tool, slash command, update hook or automatic profile scan in
this beta. Native discovery and CLI dispatch are tested in an isolated real Hermes install. See
[docs/VALIDATION.md](docs/VALIDATION.md) for current acceptance evidence; no Mac Studio
installation is implied.

## Safety and limits

Source is parsed as data with AST, never imported or executed. Git plumbing is used without
checkout, target hooks, pagers, external diffs, replacement objects or lazy fetch. Skill
symlinks, special files, oversized inputs and invalid UTF-8 are refused. File/total limits
bound input; reports escape untrusted HTML/control characters. Newly written files are private.
This is not a sandbox against a hostile local process racing filesystem changes, nor a
tamper-proof signature system. Do not publish private baselines/reports unredacted.

## Development

```sh
python -m pip install -e '.[dev]'
pytest
ruff check .
ruff format --check .
python -m build
```

Tests create disposable synthetic Git repositories; they do not commit project work or
modify your live Hermes installation. An offline demonstration is described in
[docs/TRY_IT.md](docs/TRY_IT.md).

## Feedback

Useful bug reports include the two commit IDs, package/Python/Git versions, a minimal
non-sensitive skill excerpt, expected behavior and the relevant finding or warning.
**Do not attach private baselines, credentials or unredacted reports.**
See [SECURITY.md](SECURITY.md) for the security boundary.
