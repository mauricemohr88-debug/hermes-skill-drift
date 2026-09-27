import json
from pathlib import Path

import pytest
from conftest import git, put

from hermes_skill_drift.cli import main
from hermes_skill_drift.engine import compare, snapshot
from hermes_skill_drift.git_source import GitSource
from hermes_skill_drift.report import render
from hermes_skill_drift.storage import AuditError, load_baseline


def test_ten_skills_two_committed_revisions(sample):
    repo, skills, before, after = sample
    before_files = {str(p): p.read_bytes() for p in skills.rglob("*.md")}
    repo_status = git(repo, "status", "--porcelain")
    report = compare(str(repo), before, after, [str(skills)])
    assert report["status"] == "needs_review"
    assert report["coverage"]["selected_skill_files"] == 10
    found = {Path(f["skill"]["path"]).parent.name for f in report["findings"]}
    assert found == {
        f"0{i}-{name}"
        for i, name in enumerate(["model", "tool", "voice", "cron-doc", "picker", "cron"], 1)
    }
    for finding in report["findings"]:
        assert finding["classification"] == "review_recommended"
        assert finding["skill"]["line"] == 2
        change = finding["source_change"]
        assert change["before"] or change["after"]
        for evidence in change["before"] + change["after"]:
            assert evidence["path"]
    assert report["before_commit"] == before
    assert report["after_commit"] == after
    assert report["reviewed"] is False
    assert before_files == {str(p): p.read_bytes() for p in skills.rglob("*.md")}
    assert git(repo, "status", "--porcelain") == repo_status


def test_unchanged_is_not_compatible(sample):
    repo, skills, before, _ = sample
    report = compare(str(repo), before, before, [str(skills)])
    assert report["status"] == "no_mapped_changes"
    assert not report["findings"]
    assert "not a clean bill of health" in render(report, "markdown")


def test_source_only_skips_dirty_worktree(sample):
    repo, skills, _, after = sample
    put(repo, "hermes_cli/main.py", "raise RuntimeError('not committed')\n")
    report = compare(str(repo), after, after, [str(skills)])
    assert not report["findings"]
    assert "not committed" in (repo / "hermes_cli/main.py").read_text()


def test_missing_baseline_exit2(sample, tmp_path, capsys):
    repo, skills, _, _ = sample
    code = main(
        [
            "check",
            "--repo",
            str(repo),
            "--skills",
            str(skills),
            "--baseline",
            str(tmp_path / "absent.json"),
            "--format",
            "json",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 2
    assert result["status"] == "baseline_unavailable"
    assert result["reviewed"] is False


def test_snapshot_and_check_installs_no_state(sample, tmp_path, capsys):
    repo, skills, before, after = sample
    baseline = tmp_path / "baseline.json"
    assert (
        main(
            [
                "baseline",
                "--repo",
                str(repo),
                "--ref",
                before,
                "--skills",
                str(skills),
                "--output",
                str(baseline),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert load_baseline(baseline)["reviewed"] is False
    assert baseline.stat().st_mode & 0o777 == 0o600
    original = baseline.read_bytes()
    assert (
        main(
            [
                "check",
                "--repo",
                str(repo),
                "--after",
                after,
                "--skills",
                str(skills),
                "--baseline",
                str(baseline),
                "--format",
                "json",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["baseline_kind"] == "snapshot"
    assert baseline.read_bytes() == original


def test_baseline_integrity_and_wrong_repo(sample, tmp_path):
    repo, skills, before, after = sample
    state = snapshot(str(repo), before, [str(skills)])
    state["repo"] = str(tmp_path / "other")
    with pytest.raises(AuditError, match="does not match"):
        compare(str(repo), before, after, [str(skills)], state)
    state["skills"][0]["text"] += "changed"
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state))
    with pytest.raises(AuditError, match="hash mismatch"):
        load_baseline(path)


def test_skill_changes_since_snapshot(sample):
    repo, skills, before, after = sample
    state = snapshot(str(repo), before, [str(skills)])
    put(skills, "08-control/SKILL.md", "A changed skill, not reviewed.\n")
    report = compare(str(repo), before, after, [str(skills)], state)
    assert len(report["skill_changes_since_snapshot"]) == 1
    assert report["status"] == "partial"
    assert report["reviewed"] is False


def test_removed_skill_reference_cannot_silently_pass_snapshot_check(sample):
    repo, skills, before, after = sample
    selected = skills / "01-model" / "SKILL.md"
    state = snapshot(str(repo), before, [str(selected)])
    selected.write_text("The old instruction was removed.\n")
    report = compare(str(repo), before, after, [str(selected)], state)
    assert not report["findings"]
    assert report["status"] == "partial"
    assert any("current text only" in warning for warning in report["warnings"])


def test_missing_referenced_blob_has_no_fabricated_diff(sample, monkeypatch):
    repo, skills, before, after = sample
    original = GitSource.texts

    def unavailable_text(self, tree, paths):
        texts, warnings = original(self, tree, paths)
        if any(not p.endswith(".py") for p in paths):
            return {}, warnings + ["Synthetic missing referenced document"]
        return texts, warnings

    monkeypatch.setattr(GitSource, "texts", unavailable_text)
    report = compare(str(repo), before, after, [str(skills)])
    assert report["status"] == "partial"
    paths = [
        f["source_change"] for f in report["findings"] if f["reason"] == "referenced_file_change"
    ]
    assert paths
    for change in paths:
        assert change["diff_available"] is False
        assert change["diff_excerpt"] == ""
    assert "Source diff unavailable" in render(report, "markdown")


def test_added_skill_lacks_baseline(sample):
    repo, skills, before, after = sample
    state = snapshot(str(repo), before, [str(skills)])
    put(skills, "11-new/SKILL.md", "New skill.\n")
    result = compare(str(repo), before, after, [str(skills)], state)
    assert result["status"] == "partial"
    assert result["warnings"]


def test_source_parse_error_is_partial(sample):
    repo, skills, before, _ = sample
    put(repo, "tools/bad.py", "def invalid(\n")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "Unsupported source syntax")
    result = compare(str(repo), before, "HEAD", [str(skills)])
    assert result["status"] == "partial"
    assert result["warnings"]


def test_git_revisions_cannot_be_options(sample):
    repo, _, _, _ = sample
    source = GitSource(str(repo))
    for bad in ("--help", "", "HEAD\nHEAD"):
        with pytest.raises(AuditError):
            source.resolve(bad)


def test_missing_blob_metadata_is_not_empty_source(sample, monkeypatch):
    repo, _, _, _ = sample
    source = GitSource(str(repo))
    monkeypatch.setattr(
        source,
        "run",
        lambda *args, **kwargs: b"100644 blob " + b"a" * 40 + b" BAD\ttools/missing.py\0",
    )
    tree = source.tree("a" * 40)
    assert tree["tools/missing.py"]["size"] is None
    texts, warnings = source.texts(tree, ["tools/missing.py"])
    assert texts == {}
    assert "no automatic fetch" in warnings[0]


def test_non_hermes_tree_is_partial(tmp_path):
    repo = tmp_path / "unrelated"
    repo.mkdir()
    git(repo, "init", "--quiet")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Test Fixture")
    put(repo, "tools/only.py", "# placeholder")
    put(repo, "skills/SKILL.md", "This repository has no native interface.\n")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "Unrelated fixture")
    report = compare(str(repo), "HEAD", "HEAD", [str(repo / "skills")])
    assert report["status"] == "partial"
    assert report["coverage"]["before_capabilities"] == 0
    assert any("empty coverage" in warning for warning in report["warnings"])


def test_dynamic_tool_schema_is_not_mislabeled_removed(sample):
    repo, skills, before, _ = sample
    put(repo, "tools/dynamic.py", '{"name":"terminal","parameters":make_schema()}\n')
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "Dynamic schema fixture")
    report = compare(str(repo), before, "HEAD", [str(skills)])
    relevant = [f for f in report["findings"] if f["source_change"]["key"] == "terminal"]
    assert relevant
    assert all(f["source_change"]["change"] == "not_comparable" for f in relevant)
    assert all(f["source_change"]["after"] for f in relevant)


def test_missing_revision_cli_has_structured_failure(sample, capsys):
    repo, skills, _, after = sample
    assert (
        main(
            [
                "compare",
                "--repo",
                str(repo),
                "--before",
                "nonexistent-ref",
                "--after",
                after,
                "--skills",
                str(skills),
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["status"] == "baseline_unavailable"


def test_directory_without_selected_files_not_clean(sample, tmp_path, capsys):
    repo, _, before, after = sample
    empty = tmp_path / "empty"
    empty.mkdir()
    assert (
        main(
            [
                "compare",
                "--repo",
                str(repo),
                "--before",
                before,
                "--after",
                after,
                "--skills",
                str(empty),
                "--format",
                "json",
            ]
        )
        == 2
    )
    assert "No Markdown skills" in capsys.readouterr().out


def test_git_modes_never_follow_symlinks(sample):
    repo, skills, before, _ = sample
    (repo / "tools/linked.py").symlink_to("/etc/passwd")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "Synthetic symlink")
    report = compare(str(repo), before, "HEAD", [str(skills)])
    assert report["status"] == "partial"
    assert any("non-regular" in w for w in report["warnings"])


def test_shell_hooks_and_environment_are_not_executed(sample, tmp_path, monkeypatch):
    repo, skills, before, after = sample
    sentinel = tmp_path / "SHOULD_NOT_EXIST"
    hook = tmp_path / "hook.sh"
    hook.write_text(f"#!/bin/sh\ntouch '{sentinel}'\n")
    hook.chmod(0o700)
    git(repo, "config", "core.fsmonitor", str(hook))
    git(repo, "config", "diff.external", str(hook))
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", str(hook))
    monkeypatch.setenv("GIT_DIR", "/nonexistent/override")
    compare(str(repo), before, after, [str(skills)])
    assert not sentinel.exists()


def test_report_escapes_untrusted_evidence(sample):
    repo, skills, before, after = sample
    put(skills, "01-model/SKILL.md", "<script>bad</script> `hermes model --legacy`\x1b[31m\n")
    report = render(compare(str(repo), before, after, [str(skills)]), "markdown")
    assert "<script>" not in report
    assert "\x1b" not in report
    assert "&lt;script&gt;" in report


@pytest.mark.parametrize("invalid", ["{}", "null", "[]", "{", '{"schema_version":2}'])
def test_bad_baseline(invalid, tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(invalid)
    with pytest.raises(AuditError):
        load_baseline(path)
