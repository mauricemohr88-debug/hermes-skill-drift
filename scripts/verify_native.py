"""Exercise a real Hermes CLI with this package installed, without a live profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--skills", required=True, type=Path)
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--expect", type=int, choices=(0, 1, 2), required=True)
    args = parser.parse_args()
    skills = args.skills.resolve(strict=True)
    files = [skills] if skills.is_file() else sorted(skills.rglob("*.md"))
    before_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    with tempfile.TemporaryDirectory(prefix="skill-drift-native-") as temporary:
        base = Path(temporary).resolve()
        home, profile = base / "home", base / "profile"
        home.mkdir()
        profile.mkdir()
        (profile / "config.yaml").write_text(
            "plugins:\n  enabled: [skill-drift]\n", encoding="utf-8"
        )
        # A minimal child environment prevents inherited credentials or profile overrides.
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(home),
            "HERMES_HOME": str(profile),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": "en_US.UTF-8",
            "NO_COLOR": "1",
        }

        def run(arguments: list[str], expected: int) -> subprocess.CompletedProcess:
            result = subprocess.run(
                [str(args.hermes.resolve()), "skill-drift", *arguments],
                env=env,
                cwd=base,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            if result.returncode != expected:
                raise RuntimeError(
                    f"Native Hermes returned {result.returncode}, expected {expected}:\n"
                    f"{result.stdout}\n{result.stderr}"
                )
            return result

        assert "baseline" in run(["--help"], 0).stdout
        common = ["--repo", str(args.repo.resolve()), "--skills", str(skills)]
        result = run(
            [
                "compare",
                *common,
                "--before",
                args.before,
                "--after",
                args.after,
                "--format",
                "json",
            ],
            args.expect,
        )
        # Hermes may print one-time migrations before dispatch; the report is last.
        marker = result.stdout.find('{\n  "schema_version"')
        if marker < 0:
            raise RuntimeError(f"Native command produced no JSON report: {result.stdout}")
        report = json.loads(result.stdout[marker:])
        assert report["reviewed"] is False
        baseline = base / "snapshot.json"
        run(["baseline", *common, "--ref", args.before, "--output", str(baseline)], 0)
        snapshot_hash = hashlib.sha256(baseline.read_bytes()).hexdigest()
        run(
            ["check", *common, "--baseline", str(baseline), "--after", args.after],
            args.expect,
        )
        assert hashlib.sha256(baseline.read_bytes()).hexdigest() == snapshot_hash
        run(["check", *common, "--baseline", str(base / "missing.json")], 2)
    assert before_hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    print(
        json.dumps(
            {
                "native_cli": "passed",
                "status": report["status"],
                "findings": len(report["findings"]),
                "coverage": report["coverage"],
                "input_hashes_unchanged": True,
                "live_profile_used": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
