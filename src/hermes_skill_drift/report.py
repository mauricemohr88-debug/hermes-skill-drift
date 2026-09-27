"""Plain Markdown report. Source material is quoted as untrusted evidence."""

from __future__ import annotations

import html
import json
import re
import unicodedata
from collections import Counter


def plain(value: object, *, multiline: bool = False) -> str:
    # Prevent source-controlled Markdown/HTML/terminal escapes from becoming active output.
    text = "".join(
        c
        if (c == "\n" and multiline)
        or unicodedata.category(c) not in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        else f"\\u{ord(c):04x}"
        for c in str(value)
    )
    return html.escape(text, quote=False).replace("`", "&#96;").replace("[", "&#91;")


def render(report: dict, format_name: str) -> str:
    if format_name == "json":
        return json.dumps(report, indent=2, ensure_ascii=True) + "\n"
    lines = [
        "# Hermes Skill Drift Check",
        "",
        f"Status: **{plain(report['status'])}**",
        "",
        "Read-only static review aid. No skill has been marked reviewed or runtime-compatible.",
        "",
    ]
    if report.get("error"):
        lines.extend([plain(report["error"]), ""])
    if "before_commit" not in report:
        return "\n".join(lines) + "\n"
    lines += [
        f"Before: {plain(report['before_commit'])}",
        f"After: {plain(report['after_commit'])}",
        f"Repository: {plain(report['repo'])}",
        "",
        "## Measured scope",
        "",
    ]
    lines += [f"- {plain(k)}: {v}" for k, v in report["coverage"].items()]
    lines += ["", f"## Findings ({len(report['findings'])})", ""]
    if not report["findings"]:
        lines += [
            "No mapped changes in the inspected static coverage. "
            "This is not a clean bill of health.",
            "",
        ]
    for i, finding in enumerate(report["findings"], 1):
        skill, change = finding["skill"], finding["source_change"]
        lines += [
            f"### {i}. {plain(change['key'])} — {plain(change['change'])}",
            "",
            f"Review recommended · {plain(skill['path'])}:{skill['line']}",
            "",
            "> " + plain(skill["excerpt"], multiline=True).replace("\n", "\n> "),
            "",
        ]
        for side in ("before", "after"):
            if not change[side]:
                lines.append(
                    f"- {side}: not present in this extracted surface/tree (not runtime proof)"
                )
            for source in change[side]:
                lines.append(
                    f"- {side}: {plain(source['path'])}:{source.get('line', 'object')}"
                    f" @ {report[side + '_commit']}"
                )
                if source.get("excerpt"):
                    lines.append(
                        "  > " + plain(source["excerpt"], multiline=True).replace("\n", "\n  > ")
                    )
        if change.get("diff_available") is False:
            lines += ["", "Source diff unavailable: required text was not readable."]
        if change.get("diff_excerpt"):
            lines += [
                "",
                "Source diff (untrusted quoted data):",
                "",
                "> " + plain(change["diff_excerpt"], multiline=True).replace("\n", "\n> "),
            ]
        lines.append("")
    if report["skill_changes_since_snapshot"]:
        lines += ["## Skill changes since snapshot", ""]
        lines += [
            f"- {plain(s['path'])}: {s['before_sha256']} → {s['after_sha256']}"
            for s in report["skill_changes_since_snapshot"]
        ]
        lines.append("")
    lines += [f"## Coverage warnings ({len(report['warnings'])})", ""]
    groups = Counter(
        re.sub(r" at line \d+.*$", "", warning.split(": ")[-1]) for warning in report["warnings"]
    )
    if groups:
        lines += ["Grouped limitations (not a count of broken skills):", ""]
        lines += [f"- {count}: {plain(kind)}" for kind, count in groups.most_common(8)]
        lines += ["", "First source locations:", ""]
    lines += [f"- {plain(w)}" for w in report["warnings"][:20]] or [
        "None reported by the supported extractors."
    ]
    if len(report["warnings"]) > 20:
        lines += [
            f"- {len(report['warnings']) - 20} additional coverage warnings. "
            "Use --format json for the complete list."
        ]
    lines += ["", "## Limits", ""] + [f"- {plain(s)}" for s in report["limitations"]]
    return "\n".join(lines) + "\n"
