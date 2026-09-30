"""Build and verify a self-contained, synthetic Skill Drift demonstration."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from .engine import compare, snapshot
from .report import render
from .storage import AuditError, collect_skills, load_baseline, no_links, write_new


def _put(root: Path, name: str, text: str) -> None:
    target = root / name
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    write_new(target, text)


def _git(repo: Path, env: dict[str, str], *command: str) -> str:
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        try:
            result = subprocess.run(
                [
                    "git",
                    "--no-pager",
                    "-c",
                    "user.name=Skill Drift Demo",
                    "-c",
                    "user.email=demo@example.invalid",
                    "-c",
                    "commit.gpgsign=false",
                    "-c",
                    "tag.gpgsign=false",
                    "-c",
                    "core.fsmonitor=false",
                    "-c",
                    f"core.hooksPath={os.devnull}",
                    "-c",
                    "protocol.allow=never",
                    "-C",
                    str(repo),
                    *command,
                ],
                env=env,
                stdout=output,
                stderr=errors,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AuditError(f"Synthetic demo Git operation failed: {exc}") from exc
        if output.tell() > 4096 or errors.tell() > 4096:
            raise AuditError("Synthetic demo Git output exceeded 4 KB")
        errors.seek(0)
        detail = errors.read().decode("utf-8", errors="replace").strip()
        if result.returncode:
            raise AuditError(f"Synthetic demo Git operation failed: {detail or result.returncode}")
        output.seek(0)
        return output.read().decode("utf-8", errors="replace").strip()


def _git_env(root: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_PAGER": "cat",
            "XDG_CONFIG_HOME": str(root),
        }
    )
    return env


def create_demo(directory: Path | str | None = None) -> dict[str, str]:
    """Create only a new private directory with two inert commits and ten Markdown skills."""

    if directory is None:
        temporary_parent = no_links(Path(tempfile.gettempdir()).resolve())
        root = no_links(
            Path(tempfile.mkdtemp(prefix="hermes-skill-drift-demo-", dir=temporary_parent))
        )
    else:
        root = no_links(Path(directory))
        try:
            root.mkdir(mode=0o700, parents=False, exist_ok=False)
        except OSError as exc:
            raise AuditError(f"Demo requires a new directory: {root}: {exc}") from exc
    repo, skills = root / "source", root / "skills"
    repo.mkdir(mode=0o700)
    skills.mkdir(mode=0o700)
    template = root / "empty-git-template"
    template.mkdir(mode=0o700)
    env = _git_env(root)
    _git(repo, env, "init", "--quiet", f"--template={template}")
    for stage in ("before", "after"):
        flag = "--legacy" if stage == "before" else "--refresh"
        cli_source = (
            "# Synthetic interface, not copied from Hermes.\n"
            'raise RuntimeError("Scanned source must never be executed")\n'
            "def build(subparsers):\n"
            '    model = subparsers.add_parser("model")\n'
            f'    model.add_argument("{flag}", action="store_true")\n'
        )
        tool_source = (
            "SCHEMA = "
            + repr(
                {
                    "name": "demo_tool",
                    "parameters": {"type": "object", "properties": {"mode": {"enum": [stage]}}},
                }
            )
            + "\n"
        )
        if stage == "before":
            _put(repo, "hermes_cli/main.py", cli_source)
            _put(repo, "tools/demo.py", tool_source)
            _put(repo, "docs/guide.md", "Documented behavior: before.\n")
            _put(repo, "docs/old-guide.md", "Old path.\n")
        else:
            (repo / "hermes_cli/main.py").write_text(cli_source, encoding="utf-8")
            (repo / "tools/demo.py").write_text(tool_source, encoding="utf-8")
            (repo / "docs/guide.md").write_text("Documented behavior: after.\n", encoding="utf-8")
            (repo / "docs/old-guide.md").rename(repo / "docs/new-guide.md")
        _git(repo, env, "add", ".")
        _git(repo, env, "commit", "--quiet", "-m", f"Synthetic {stage} interface")
        _git(repo, env, "tag", stage)

    texts = [
        "Run `hermes model --legacy`.",
        "Use `demo_tool`.",
        "Read `docs/old-guide.md`.",
        "Read `docs/guide.md`.",
        "Start `hermes model`.",
        "Summarize notes.",
        "Explain a paragraph.",
        "Sort three titles.",
        "Use `hermes modelx --legacy` as a prefix control.",
        "Check spelling manually.",
    ]
    for index, text in enumerate(texts, 1):
        _put(skills, f"skill-{index:02d}/SKILL.md", f"# Demo skill {index}\n{text}\n")
    return {
        "demo": str(root),
        "source": str(repo),
        "skills": str(skills),
        "before": _git(repo, env, "rev-parse", "before"),
        "after": _git(repo, env, "rev-parse", "after"),
    }


def run_demo(directory: Path | str | None = None) -> tuple[dict[str, str], dict]:
    """Persist the evidence and require the known synthetic case to match expectations."""

    details = create_demo(directory)
    root = Path(details["demo"])
    baseline_path, report_path, json_path = (
        root / "baseline.json",
        root / "report.md",
        root / "report.json",
    )
    baseline = snapshot(details["source"], details["before"], [details["skills"]])
    write_new(baseline_path, json.dumps(baseline, indent=2, ensure_ascii=True) + "\n")
    saved = load_baseline(baseline_path)
    current_skills = collect_skills([details["skills"]])
    if saved != baseline or current_skills != saved["skills"]:
        raise AuditError("Synthetic demo baseline or skill contents failed integrity checks")
    baseline_bytes = baseline_path.read_bytes()
    report = compare(
        details["source"],
        details["before"],
        details["after"],
        [details["skills"]],
        saved,
    )
    if (
        baseline_path.read_bytes() != baseline_bytes
        or load_baseline(baseline_path) != saved
        or collect_skills([details["skills"]]) != current_skills
    ):
        raise AuditError("Synthetic demo scan changed baseline or skill contents")
    try:
        actual = {
            (
                Path(finding["skill"]["path"]).relative_to(details["skills"]).as_posix(),
                finding["skill"]["line"],
                finding["source_change"]["key"],
                finding["source_change"]["change"],
            )
            for finding in report["findings"]
        }
    except ValueError as exc:
        raise AuditError("Synthetic demo finding escaped its selected skill directory") from exc
    expected = {
        ("skill-01/SKILL.md", 2, "hermes model --legacy", "removed"),
        ("skill-01/SKILL.md", 2, "hermes model --refresh", "added"),
        ("skill-02/SKILL.md", 2, "demo_tool", "changed"),
        ("skill-03/SKILL.md", 2, "docs/old-guide.md", "removed"),
        ("skill-04/SKILL.md", 2, "docs/guide.md", "changed"),
        ("skill-05/SKILL.md", 2, "hermes model --refresh", "added"),
    }
    if (
        report["status"] != "needs_review"
        or len(report["findings"]) != len(expected)
        or actual != expected
        or len(current_skills) != 10
        or report["skill_changes_since_snapshot"]
        or report["reviewed"] is not False
    ):
        raise AuditError("Synthetic demo did not produce the expected six review findings")
    repo = Path(details["source"])
    env = _git_env(root)
    if (
        _git(repo, env, "status", "--porcelain")
        or _git(repo, env, "rev-parse", "before") != details["before"]
        or _git(repo, env, "rev-parse", "after") != details["after"]
    ):
        raise AuditError("Synthetic demo repository changed after scanning")
    write_new(report_path, render(report, "markdown"))
    write_new(json_path, render(report, "json"))
    if not report_path.stat().st_size or not json_path.stat().st_size:
        raise AuditError("Synthetic demo report was not saved")
    details.update(
        {"baseline": str(baseline_path), "report": str(report_path), "report_json": str(json_path)}
    )
    return details, report
