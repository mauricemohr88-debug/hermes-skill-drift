"""Fail before publication if tracked files leak local review data or machine paths."""

import re
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = re.compile(rb"/(?:Users|home)/[A-Za-z0-9_.-]+/|/private/tmp/[A-Za-z0-9]")
BLOCKED = ("review-", "PUBLIC-SOURCE-", "DEMO-REPORT", "baseline.json", ".env")


def check(name: str, data: bytes) -> None:
    if Path(name).name.startswith(BLOCKED) or PRIVATE.search(data):
        raise SystemExit(f"Private publication content detected: {name}")


def main() -> None:
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).split(b"\0")
    for raw in tracked:
        if raw:
            path = ROOT / raw.decode()
            check(str(path.relative_to(ROOT)), path.read_bytes())
    archives = []
    for path in (ROOT / "dist").glob("*.whl"):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                check(name, archive.read(name))
        archives.append(path.name)
    for path in (ROOT / "dist").glob("*.tar.gz"):
        with tarfile.open(path) as archive:
            for item in archive:
                if item.isfile():
                    stream = archive.extractfile(item)
                    assert stream is not None
                    check(item.name, stream.read())
        archives.append(path.name)
    print(f"Publication audit passed: {len(tracked) - 1} tracked files; {len(archives)} archives")


if __name__ == "__main__":
    main()
