import argparse
import os
from types import SimpleNamespace

import pytest

from hermes_skill_drift.plugin import register
from hermes_skill_drift.storage import (
    AuditError,
    collect_skills,
    load_baseline,
    read_text,
    write_new,
)


def test_symbolic_links_rejected(tmp_path):
    secret = tmp_path / "private.txt"
    secret.write_text("SECRET")
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "SKILL.md").symlink_to(secret)
    with pytest.raises(AuditError, match="Symbolic"):
        collect_skills([str(skills)])


def test_linked_directory_rejected(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "nested").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(AuditError):
        collect_skills([str(skills)])


def test_fifo_is_not_read(tmp_path):
    path = tmp_path / "SKILL.md"
    os.mkfifo(path)
    with pytest.raises(AuditError):
        read_text(path)


def test_limit_and_encoding(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text("a" * 40)
    with pytest.raises(AuditError):
        read_text(path, limit=10)
    path.write_bytes(b"\xff")
    with pytest.raises(AuditError):
        read_text(path)


def test_duplicate_json_keys_are_rejected(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text('{"schema_version":2,"schema_version":1}')
    with pytest.raises(AuditError, match="duplicate JSON key"):
        load_baseline(path)


def test_output_never_overwrites(tmp_path):
    path = tmp_path / "report.md"
    write_new(path, "first")
    with pytest.raises(AuditError):
        write_new(path, "second")
    assert path.read_text() == "first"
    link = tmp_path / "link.md"
    link.symlink_to(path)
    with pytest.raises(AuditError):
        write_new(link, "second")
    assert path.read_text() == "first"


def test_explicit_selection_only(tmp_path):
    (tmp_path / "SKILL.md").write_text("visible")
    (tmp_path / ".secrets.md").write_text("hidden")
    (tmp_path / "tokens.json").write_text("private")
    selected = collect_skills([str(tmp_path), str(tmp_path / "SKILL.md")])
    assert len(selected) == 1
    assert selected[0]["text"] == "visible"


def test_plugin_cli_contract_only(sample, capsys):
    registrations = []
    ctx = SimpleNamespace(register_cli_command=lambda **kwargs: registrations.append(kwargs))
    register(ctx)
    assert len(registrations) == 1
    entry = registrations[0]
    assert entry["name"] == "skill-drift"
    parser = argparse.ArgumentParser()
    entry["setup_fn"](parser)
    repo, skills, before, after = sample
    args = parser.parse_args(
        [
            "compare",
            "--repo",
            str(repo),
            "--before",
            before,
            "--after",
            after,
            "--skills",
            str(skills),
        ]
    )
    assert entry["handler_fn"](args) == 1
    assert "Review recommended" in capsys.readouterr().out
