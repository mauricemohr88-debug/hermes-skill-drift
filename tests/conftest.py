from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

BEFORE = """import argparse
from pathlib import Path
raise RuntimeError("SCANNED SOURCE MUST NEVER EXECUTE")

def build(subparsers):
    model = subparsers.add_parser("model")
    model.add_argument("--legacy", action="store_true")
    model.add_argument("--stable", default="keep")
    cron = subparsers.add_parser("cron")
    subs = cron.add_subparsers()
    create = subs.add_parser("create")
    create.add_argument("--attach", action="store_true")
"""
AFTER = """import argparse
raise RuntimeError("SCANNED SOURCE MUST NEVER EXECUTE")

def build(subparsers):
    model = subparsers.add_parser("model")
    model.add_argument("--refresh", action="store_true")
    model.add_argument("--stable", default="keep")
    cron = subparsers.add_parser("cron")
    subs = cron.add_subparsers()
    create = subs.add_parser("create")
    create.add_argument("--continuity", action="store_true")
"""
SKILLS = {
    "01-model/SKILL.md": "# Refresh\nRun `hermes model --legacy` to refresh.\n",
    "02-tool/SKILL.md": "# Execution\nUse `terminal` with the mode parameter.\n",
    "03-voice/SKILL.md": "# Voice\nFollow `docs/voice-old.md`.\n",
    "04-cron-doc/SKILL.md": "# Delivery\nRead `docs/cron.md` before scheduling.\n",
    "05-picker/SKILL.md": "# Picker\nStart `hermes model`.\n",
    "06-cron/SKILL.md": "# Cron\nRun `hermes cron create --attach`.\n",
    "07-stable/SKILL.md": "# Stable\nRead `docs/stable.md`.\n",
    "08-control/SKILL.md": "# Notes\nSummarize three notes without changing them.\n",
    "09-prefix/SKILL.md": "# Prefix control\n`hermes modelx --legacy` is a made-up example.\n",
    "10-python/SKILL.md": "# Python\nNo native commands are referenced here.\n",
}


def git(repo: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    return subprocess.check_output(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-C",
            str(repo),
            *args,
        ],
        env=env,
        text=True,
        stderr=subprocess.PIPE,
    ).strip()


def put(repo: Path, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def create_fixture(root: Path) -> tuple[Path, Path, str, str]:
    repo, skills = root / "source", root / "skills"
    repo.mkdir(parents=True)
    skills.mkdir()
    git(repo, "init", "--quiet")
    put(repo, "hermes_cli/main.py", BEFORE)
    put(
        repo,
        "tools/terminal.py",
        'SCHEMA = {"name":"terminal", "parameters": {"type":"object", '
        '"properties":{"mode":{"enum":["old"]}}}}\n',
    )
    put(repo, "docs/voice-old.md", "Use the old voice guide.\n")
    put(repo, "docs/cron.md", "Continuity includes all session history.\n")
    put(repo, "docs/stable.md", "This instruction is unchanged.\n")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "Synthetic before state")
    before = git(repo, "rev-parse", "HEAD")
    put(repo, "hermes_cli/main.py", AFTER)
    put(
        repo,
        "tools/terminal.py",
        'SCHEMA = {"name":"terminal", "parameters": {"type":"object", '
        '"properties":{"mode":{"enum":["new"]}}}}\n',
    )
    (repo / "docs/voice-old.md").rename(repo / "docs/voice-new.md")
    put(repo, "docs/cron.md", "Continuity includes previous job output, not session history.\n")
    git(repo, "add", ".")
    git(repo, "commit", "--quiet", "-m", "Synthetic after state")
    after = git(repo, "rev-parse", "HEAD")
    for path, text in SKILLS.items():
        put(skills, path, text)
    return repo, skills, before, after


@pytest.fixture
def sample(tmp_path):
    return create_fixture(tmp_path)
