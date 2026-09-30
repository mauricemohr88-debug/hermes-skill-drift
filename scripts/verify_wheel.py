"""Install the built wheel offline into a new environment and exercise the public CLI."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

from hermes_skill_drift import __version__

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    wheel = ROOT / "dist" / f"hermes_skill_drift-{__version__}-py3-none-any.whl"
    if not wheel.is_file():
        raise SystemExit("Build the current wheel first")
    with tempfile.TemporaryDirectory(prefix="skill-drift-wheel-") as temporary:
        base = Path(temporary).resolve()
        environment = base / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / "bin" / "python"
        cli = environment / "bin" / "hermes-skill-drift"
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
            check=True,
            cwd=base,
        )
        demo = base / "demo"
        subprocess.run(
            [sys.executable, str(ROOT / "examples/create_demo.py"), str(demo)], check=True
        )
        files = sorted((demo / "skills").rglob("*.md"))
        original = [hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
        common = ["--repo", str(demo / "source"), "--skills", str(demo / "skills")]
        env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}

        def run(arguments: list[str], expected: int) -> str:
            result = subprocess.run(
                [str(cli), *arguments],
                cwd=base,
                env=env,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
            return result.stdout

        assert run(["--version"], 0).strip() == __version__
        packaged_demo = base / "packaged-demo"
        preview = run(["demo", "--directory", str(packaged_demo)], 0)
        bundled_report = json.loads((packaged_demo / "report.json").read_text(encoding="utf-8"))
        assert bundled_report["status"] == "needs_review"
        assert bundled_report["reviewed"] is False
        assert len(bundled_report["findings"]) == 6
        expected_affected = {
            str(packaged_demo / "skills" / f"skill-{number:02d}" / "SKILL.md")
            for number in range(1, 6)
        }
        assert {item["skill"]["path"] for item in bundled_report["findings"]} == expected_affected
        actual_mappings = {
            (
                str(Path(item["skill"]["path"]).relative_to(packaged_demo / "skills")),
                item["skill"]["line"],
                item["source_change"]["key"],
                item["source_change"]["change"],
            )
            for item in bundled_report["findings"]
        }
        assert actual_mappings == {
            ("skill-01/SKILL.md", 2, "hermes model --legacy", "removed"),
            ("skill-01/SKILL.md", 2, "hermes model --refresh", "added"),
            ("skill-02/SKILL.md", 2, "demo_tool", "changed"),
            ("skill-03/SKILL.md", 2, "docs/old-guide.md", "removed"),
            ("skill-04/SKILL.md", 2, "docs/guide.md", "changed"),
            ("skill-05/SKILL.md", 2, "hermes model --refresh", "added"),
        }
        assert "--legacy" in preview and "needs_review" in preview
        assert (packaged_demo / "report.md").is_file()
        packaged_hashes = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in packaged_demo.rglob("*")
            if path.is_file()
        }
        run(["demo", "--directory", str(packaged_demo)], 2)
        assert packaged_hashes == {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in packaged_demo.rglob("*")
            if path.is_file()
        }
        report = json.loads(
            run(
                [
                    "compare",
                    *common,
                    "--before",
                    "before",
                    "--after",
                    "after",
                    "--format",
                    "json",
                ],
                1,
            )
        )
        assert report["status"] == "needs_review" and len(report["findings"]) == 6
        assert len({f["skill"]["path"] for f in report["findings"]}) == 5
        baseline = base / "snapshot.json"
        run(["baseline", *common, "--ref", "before", "--output", str(baseline)], 0)
        digest = hashlib.sha256(baseline.read_bytes()).hexdigest()
        run(["check", *common, "--baseline", str(baseline), "--after", "after"], 1)
        assert hashlib.sha256(baseline.read_bytes()).hexdigest() == digest
        run(["baseline", *common, "--ref", "before", "--output", str(baseline)], 2)
        run(["check", *common, "--baseline", str(base / "missing.json")], 2)
        assert original == [hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
        probe = subprocess.check_output(
            [
                str(python),
                "-I",
                "-c",
                "from importlib.metadata import distribution; "
                "e=next(e for e in distribution('hermes-skill-drift').entry_points "
                "if e.group=='hermes_agent.plugins'); assert callable(e.load().register); "
                "import hermes_skill_drift; print(hermes_skill_drift.__file__)",
            ],
            cwd=base,
            env=env,
            text=True,
        )
        assert str(environment) in probe
    print(
        "Fresh-wheel packaged demo, CLI, snapshot integrity, refusal cases "
        "and plugin entry point: passed"
    )


if __name__ == "__main__":
    main()
