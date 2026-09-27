"""Explicit local paths; no discovery of credentials or live profiles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .engine import compare, snapshot
from .report import render
from .storage import AuditError, load_baseline, write_new


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="drift_action", required=True)
    baseline = commands.add_parser(
        "baseline", help="Record an unreviewed local source/skill snapshot"
    )
    baseline.add_argument("--repo", required=True)
    baseline.add_argument("--ref", default="HEAD")
    baseline.add_argument("--skills", action="append", required=True, metavar="PATH")
    baseline.add_argument("--output", required=True, metavar="NEW_JSON_FILE")
    for name in ("compare", "check"):
        command = commands.add_parser(
            name,
            help=(
                "Compare two committed source revisions"
                if name == "compare"
                else "Compare saved baseline to a revision"
            ),
        )
        command.add_argument("--repo", required=True)
        if name == "compare":
            command.add_argument("--before", required=True)
        else:
            command.add_argument("--baseline", required=True)
        command.add_argument("--after", default="HEAD")
        command.add_argument("--skills", action="append", required=True, metavar="PATH")
        command.add_argument("--format", choices=("markdown", "json"), default="markdown")
        command.add_argument("--output", metavar="NEW_REPORT_FILE")


def execute(args: argparse.Namespace) -> int:
    try:
        if args.drift_action == "baseline":
            data = snapshot(args.repo, args.ref, args.skills)
            write_new(Path(args.output), json.dumps(data, indent=2, ensure_ascii=True) + "\n")
            print(f"Snapshot saved: {args.output}\nCommit: {data['commit']}\nNot marked reviewed.")
            return 0
        baseline = load_baseline(Path(args.baseline)) if args.drift_action == "check" else None
        before = baseline["commit"] if baseline else args.before
        report = compare(args.repo, before, args.after, args.skills, baseline)
        code = 2 if report["status"] == "partial" else 1 if report["findings"] else 0
    except (AuditError, OSError, RecursionError) as exc:
        if args.drift_action == "baseline":
            print(f"Snapshot not saved: {exc}", file=sys.stderr)
            return 2
        report = {
            "schema_version": 1,
            "kind": "skill_drift_report",
            "reviewed": False,
            "status": "baseline_unavailable",
            "error": str(exc),
            "findings": [],
        }
        code = 2
    output = render(report, args.format)
    try:
        if args.output:
            write_new(Path(args.output), output)
            print(f"Report saved: {args.output}\nStatus: {report['status']}")
        else:
            print(output, end="")
    except AuditError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Hermes version-to-skill review evidence"
    )
    configure(parser)
    return execute(parser.parse_args(argv))
