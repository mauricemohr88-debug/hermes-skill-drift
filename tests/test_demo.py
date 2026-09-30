import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import hermes_skill_drift.demo as demo_module
from hermes_skill_drift.cli import main
from hermes_skill_drift.demo import create_demo
from hermes_skill_drift.storage import AuditError, load_baseline


def test_demo_command_persists_expected_unreviewed_evidence(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["demo", "--directory", str(root)]) == 0
    output = capsys.readouterr().out
    assert "--refresh" in output and "NOT an automatically equivalent" in output
    assert "exits 1 for needs_review" in output
    baseline = load_baseline(root / "baseline.json")
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    markdown = (root / "report.md").read_text(encoding="utf-8")
    assert baseline["reviewed"] is False
    assert report["reviewed"] is False
    assert report["status"] == "needs_review"
    assert len(report["findings"]) == 6
    assert len({finding["skill"]["path"] for finding in report["findings"]}) == 5
    assert report["skill_changes_since_snapshot"] == []
    assert len(list((root / "skills").rglob("SKILL.md"))) == 10
    assert all(
        (root / name).stat().st_mode & 0o777 == 0o600
        for name in ("baseline.json", "report.md", "report.json")
    )
    assert root.stat().st_mode & 0o777 == 0o700
    assert "Review recommended" in markdown
    assert "No skill has been marked reviewed" in markdown
    assert "raise RuntimeError" in (root / "source/hermes_cli/main.py").read_text()
    assert (
        subprocess.check_output(
            ["git", "-C", str(root / "source"), "status", "--porcelain"], text=True
        )
        == ""
    )


def test_demo_default_is_unique_and_retained(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(demo_module.tempfile, "gettempdir", lambda: str(tmp_path))
    assert main(["demo"]) == 0
    first = capsys.readouterr().out
    assert main(["demo"]) == 0
    second = capsys.readouterr().out
    first_path = Path(first.split("Directory: ", 1)[1].splitlines()[0])
    second_path = Path(second.split("Directory: ", 1)[1].splitlines()[0])
    assert first_path != second_path
    assert first_path.joinpath("report.md").is_file()
    assert second_path.joinpath("report.json").is_file()


def test_demo_refuses_existing_directory_and_symlink_parent(tmp_path, capsys):
    existing = tmp_path / "existing"
    existing.mkdir()
    assert main(["demo", "--directory", str(existing)]) == 2
    assert "requires a new directory" in capsys.readouterr().err
    link = tmp_path / "linked"
    link.symlink_to(existing, target_is_directory=True)
    assert main(["demo", "--directory", str(link / "child")]) == 2
    assert "Symbolic links are not supported" in capsys.readouterr().err
    assert not (existing / "child").exists()


def test_demo_ignores_inherited_git_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(tmp_path / "missing-template"))
    assert main(["demo", "--directory", str(tmp_path / "demo")]) == 0
    capsys.readouterr()


def test_legacy_example_factory_shape(tmp_path):
    details = create_demo(tmp_path / "example")
    assert set(details) == {"demo", "source", "skills", "before", "after"}
    assert len(list(Path(details["skills"]).rglob("SKILL.md"))) == 10
    assert not (tmp_path / "example" / "baseline.json").exists()
    assert not (tmp_path / "example" / "report.md").exists()


def test_legacy_example_runs_from_uninstalled_checkout(tmp_path):
    script = Path(__file__).resolve().parents[1] / "examples" / "create_demo.py"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = ""
    result = subprocess.run(
        [sys.executable, "-S", str(script), str(tmp_path / "standalone")],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    details = json.loads(result.stdout)
    assert details["demo"] == str(tmp_path / "standalone")
    assert len(list(Path(details["skills"]).rglob("SKILL.md"))) == 10


@pytest.mark.parametrize("mutated", ["baseline", "skill"])
def test_demo_detects_mutation_during_compare(tmp_path, monkeypatch, mutated):
    original = demo_module.compare

    def changing_compare(repo, before, after, roots, baseline):
        report = original(repo, before, after, roots, baseline)
        if mutated == "baseline":
            path = tmp_path / "demo" / "baseline.json"
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        else:
            path = tmp_path / "demo" / "skills" / "skill-01" / "SKILL.md"
            path.write_text("changed after snapshot\n", encoding="utf-8")
        return report

    monkeypatch.setattr(demo_module, "compare", changing_compare)
    with pytest.raises(AuditError, match="changed baseline or skill contents"):
        demo_module.run_demo(tmp_path / "demo")


def test_demo_rejects_wrong_affected_control_path(tmp_path, monkeypatch):
    original = demo_module.compare

    def wrong_mapping(repo, before, after, roots, baseline):
        report = original(repo, before, after, roots, baseline)
        for finding in report["findings"]:
            if "skill-05/" in finding["skill"]["path"]:
                finding["skill"]["path"] = finding["skill"]["path"].replace(
                    "skill-05/", "skill-06/"
                )
        return report

    monkeypatch.setattr(demo_module, "compare", wrong_mapping)
    with pytest.raises(AuditError, match="expected six review findings"):
        demo_module.run_demo(tmp_path / "demo")
