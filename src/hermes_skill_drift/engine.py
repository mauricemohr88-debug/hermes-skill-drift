"""Map committed source changes to explicit references, not inferred skill intent."""

from __future__ import annotations

import difflib
import re
from datetime import datetime, timezone

from .extract import extract_source
from .git_source import GitSource
from .storage import AuditError, collect_skills

BOUNDARY_LEFT = r"(?<![\w./-])"
BOUNDARY_RIGHT = r"(?![\w/-])"
LIMITATIONS = [
    "Static evidence only: no code, skills, commands, or model prompts are executed.",
    "Only literal argparse and tool schemas are extracted. Dynamic interfaces may be missed.",
    "All findings require human review; absence of findings is not runtime compatibility.",
    "Added alternatives need an explicit command reference; intent-only matches are not inferred.",
    "Git object snapshots are compared, not uncommitted source changes or installed dependencies.",
    "No automatic update hook, skill edits, reviewed-state promotion, or network requests.",
]


def snapshot(repo_path: str, ref: str, roots: list[str]) -> dict:
    repo = GitSource(repo_path)
    return {
        "schema_version": 1,
        "kind": "skill_drift_snapshot",
        "reviewed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repo": repo.path,
        "commit": repo.resolve(ref),
        "skills": collect_skills(roots),
    }


def _catalog(repo: GitSource, tree: dict) -> tuple[dict, list[str], int]:
    paths = sorted(
        p
        for p in tree
        if p.endswith(".py") and (p.startswith("hermes_cli/") or p.startswith("tools/"))
    )
    texts, warnings = repo.texts(tree, paths)
    if not paths:
        warnings.append("No hermes_cli/ or tools/ Python sources found at this revision")
    catalog: dict[tuple[str, str], list[dict]] = {}
    for path, text in texts.items():
        extracted = extract_source(path, text)
        warnings.extend(f"{path}: {warning}" for warning in extracted["warnings"])
        for capability in extracted["capabilities"]:
            catalog.setdefault((capability["kind"], capability["key"]), []).append(capability)
    if not any(p.startswith("hermes_cli/") for p in paths):
        warnings.append("No Hermes CLI sources found; repository coverage is unverified")
    if not catalog:
        warnings.append("No native capabilities extracted; empty coverage is not a clean audit")
    # Retain every definition: multiple registration sites can be legitimate.
    return catalog, warnings, len(texts)


def _contains(text: str, token: str) -> bool:
    return re.search(BOUNDARY_LEFT + re.escape(token) + BOUNDARY_RIGHT, text) is not None


def _matches(line: str, kind: str, key: str, change: str) -> bool:
    if kind == "option":
        command, flag = key.rsplit(" ", 1)
        return _contains(line, command) and (change == "added" or _contains(line, flag))
    if change == "added":
        # A new tool or command is not a recommendation solely because it shares a vague topic.
        return _contains(line, key)
    return _contains(line, key)


def compare(
    repo_path: str, before: str, after: str, roots: list[str], baseline: dict | None = None
) -> dict:
    repo = GitSource(repo_path)
    old_sha, new_sha = repo.resolve(before), repo.resolve(after)
    if baseline and (baseline["repo"] != repo.path or baseline["commit"] != old_sha):
        raise AuditError("Baseline repository/commit does not match the selected Git source")
    skills = collect_skills(roots)
    old_tree, new_tree = repo.tree(old_sha), repo.tree(new_sha)
    old_cat, old_warnings, old_count = _catalog(repo, old_tree)
    new_cat, new_warnings, new_count = _catalog(repo, new_tree)
    warnings = [f"before: {w}" for w in old_warnings] + [f"after: {w}" for w in new_warnings]
    changes = []
    for key in sorted(old_cat.keys() | new_cat.keys()):
        old, new = old_cat.get(key, []), new_cat.get(key, [])
        old_signatures = sorted({(c.get("resolved", True), c["signature"]) for c in old})
        new_signatures = sorted({(c.get("resolved", True), c["signature"]) for c in new})
        if old and new and old_signatures == new_signatures:
            continue
        changes.append(
            {
                "kind": key[0],
                "key": key[1],
                "change": (
                    "not_comparable"
                    if any(not c.get("resolved", True) for c in old + new)
                    else "added"
                    if not old
                    else "removed"
                    if not new
                    else "changed"
                ),
                "before": old,
                "after": new,
            }
        )

    findings = []
    seen = set()
    changed_paths = {
        p
        for p in old_tree
        if p not in new_tree
        or old_tree[p]["oid"] != new_tree[p]["oid"]
        or old_tree[p]["mode"] != new_tree[p]["mode"]
    }
    referenced_paths = set()
    for skill in skills:
        for line_no, line in enumerate(skill["text"].splitlines(), 1):
            for change in changes:
                if _matches(line, change["kind"], change["key"], change["change"]):
                    identity = (skill["path"], line_no, change["kind"], change["key"])
                    if identity in seen:
                        continue
                    seen.add(identity)
                    findings.append(
                        {
                            "classification": "review_recommended",
                            "reason": "native_surface_change",
                            "skill": {
                                "path": skill["path"],
                                "line": line_no,
                                "sha256": skill["sha256"],
                                "excerpt": line[:800],
                            },
                            "source_change": change,
                        }
                    )
            # Extract path-like tokens before looking them up; avoid O(skills * repository paths).
            for raw_path in re.findall(r"(?:[\w.-]+/)+[\w.-]+", line):
                path = raw_path.removeprefix("./").rstrip(".,;")
                if path not in changed_paths:
                    continue
                identity = (skill["path"], line_no, "path", path)
                if identity in seen:
                    continue
                seen.add(identity)
                referenced_paths.add(path)
                findings.append(
                    {
                        "classification": "review_recommended",
                        "reason": "referenced_file_change",
                        "skill": {
                            "path": skill["path"],
                            "line": line_no,
                            "sha256": skill["sha256"],
                            "excerpt": line[:800],
                        },
                        "source_change": {
                            "kind": "path",
                            "key": path,
                            "change": "removed" if path not in new_tree else "changed",
                            "before": [{"path": path, **old_tree[path]}],
                            "after": [{"path": path, **new_tree[path]}] if path in new_tree else [],
                        },
                    }
                )
    old_texts, old_file_warnings = repo.texts(old_tree, sorted(referenced_paths))
    new_texts, new_file_warnings = repo.texts(new_tree, sorted(referenced_paths & new_tree.keys()))
    warnings.extend(old_file_warnings + new_file_warnings)
    for finding in findings:
        change = finding["source_change"]
        if change["kind"] == "path":
            path = change["key"]
            if path not in old_texts or (path in new_tree and path not in new_texts):
                # An unreadable blob is not an empty file; never invent a deletion diff.
                change["diff_available"] = False
                change["diff_excerpt"] = ""
                change["diff_truncated"] = False
                continue
            change["diff_available"] = True
            diff = list(
                difflib.unified_diff(
                    old_texts.get(path, "").splitlines(),
                    new_texts.get(path, "").splitlines(),
                    fromfile=f"{old_sha}:{path}",
                    tofile=f"{new_sha}:{path}",
                    lineterm="",
                    n=2,
                )
            )
            change["diff_excerpt"] = "\n".join(diff[:40])[:4000]
            change["diff_truncated"] = len(diff) > 40 or len("\n".join(diff[:40])) > 4000

    skill_changes = []
    if baseline:
        old_skills = {s["path"]: s for s in baseline["skills"]}
        new_skills = {s["path"]: s for s in skills}
        for path in sorted(old_skills.keys() | new_skills.keys()):
            old_hash = old_skills.get(path, {}).get("sha256")
            new_hash = new_skills.get(path, {}).get("sha256")
            if old_hash != new_hash:
                skill_changes.append(
                    {"path": path, "before_sha256": old_hash, "after_sha256": new_hash}
                )
        if skill_changes:
            warnings.append(
                "Skill contents changed since snapshot; findings use current text only. "
                "Changed baseline instructions have not been reviewed"
            )
        if old_skills.keys() != new_skills.keys():
            warnings.append(
                "Selected skill set differs from snapshot; some skills lack a baseline "
                "or are missing"
            )
    findings.sort(key=lambda f: (f["skill"]["path"], f["skill"]["line"], f["source_change"]["key"]))
    return {
        "schema_version": 1,
        "kind": "skill_drift_report",
        "reviewed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if warnings else "needs_review" if findings else "no_mapped_changes",
        "repo": repo.path,
        "before_commit": old_sha,
        "after_commit": new_sha,
        "baseline_kind": "snapshot" if baseline else "explicit_commit_pair",
        "skills": [{k: s[k] for k in ("path", "sha256")} for s in skills],
        "skill_changes_since_snapshot": skill_changes,
        "coverage": {
            "before_source_files": old_count,
            "after_source_files": new_count,
            "before_capabilities": len(old_cat),
            "after_capabilities": len(new_cat),
            "native_changes": len(changes),
            "selected_skill_files": len(skills),
        },
        "findings": findings,
        "warnings": sorted(set(warnings)),
        "limitations": LIMITATIONS,
    }
