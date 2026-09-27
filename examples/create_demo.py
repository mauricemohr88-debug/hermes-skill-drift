"""Create two synthetic Git commits and ten harmless skills in a new directory."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def put(root: Path, name: str, text: str) -> None:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="A new, non-existing demo directory")
    args = parser.parse_args()
    root = args.directory.expanduser().resolve()
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    repo, skills = root / "source", root / "skills"
    repo.mkdir()
    skills.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})

    def git(*command: str) -> str:
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Skill Drift Demo",
                "-c",
                "user.email=demo@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                f"core.hooksPath={os.devnull}",
                "-C",
                str(repo),
                *command,
            ],
            env=env,
            text=True,
            stderr=subprocess.PIPE,
        ).strip()

    git("init", "--quiet")
    for stage in ("before", "after"):
        flag = "--legacy" if stage == "before" else "--refresh"
        put(
            repo,
            "hermes_cli/main.py",
            f'''# Synthetic interface, not copied from Hermes.
raise RuntimeError("Scanned source must never be executed")
def build(subparsers):
    model = subparsers.add_parser("model")
    model.add_argument("{flag}", action="store_true")
''',
        )
        put(
            repo,
            "tools/demo.py",
            "SCHEMA = "
            + repr(
                {
                    "name": "demo_tool",
                    "parameters": {"type": "object", "properties": {"mode": {"enum": [stage]}}},
                }
            )
            + "\n",
        )
        put(repo, "docs/guide.md", f"Documented behavior: {stage}.\n")
        if stage == "before":
            put(repo, "docs/old-guide.md", "Old path.\n")
        else:
            (repo / "docs/old-guide.md").rename(repo / "docs/new-guide.md")
        git("add", ".")
        git("commit", "--quiet", "-m", f"Synthetic {stage} interface")
        git("tag", stage)
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
        put(skills, f"skill-{index:02d}/SKILL.md", f"# Demo skill {index}\n{text}\n")
    print(
        json.dumps(
            {
                "demo": str(root),
                "source": str(repo),
                "skills": str(skills),
                "before": git("rev-parse", "before"),
                "after": git("rev-parse", "after"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
