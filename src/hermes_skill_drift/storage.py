"""Bounded local input and exclusive, private output files."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

MAX_FILE = 1_000_000
MAX_SKILLS = 500
MAX_TOTAL = 10_000_000


class AuditError(Exception):
    """An unavailable or unsafe input must not appear as a successful audit."""


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def no_links(path: Path) -> Path:
    path = Path(os.path.abspath(path.expanduser()))
    for part in (path, *path.parents):
        if part.is_symlink():
            raise AuditError(f"Symbolic links are not supported: {part}")
    return path


def read_text(path: Path, limit: int = MAX_FILE) -> str:
    path = no_links(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise AuditError(f"Expected regular file of at most {limit} bytes: {path}")
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise AuditError(f"File exceeded size limit while reading: {path}")
        return raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise AuditError(f"Cannot read UTF-8 input {path}: {exc}") from exc


def collect_skills(roots: list[str]) -> list[dict]:
    if not roots:
        raise AuditError("Select at least one skill directory or Markdown file with --skills")
    files: set[Path] = set()
    for selected in roots:
        root = no_links(Path(selected))
        if root.is_file():
            if root.suffix.lower() != ".md":
                raise AuditError(f"Selected skill file must be Markdown: {root}")
            files.add(root)
        elif root.is_dir():

            def on_error(exc: OSError) -> None:
                raise AuditError(f"Cannot enumerate selected skill directory: {exc}")

            for directory, dirs, names in os.walk(root, followlinks=False, onerror=on_error):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                for name in dirs:
                    no_links(Path(directory) / name)
                for name in sorted(names):
                    if name.lower().endswith(".md") and not name.startswith("."):
                        files.add(no_links(Path(directory) / name))
                if len(files) > MAX_SKILLS:
                    raise AuditError(f"Too many selected Markdown files (limit {MAX_SKILLS})")
        else:
            raise AuditError(f"Selected skill input does not exist: {root}")
    if not files or len(files) > MAX_SKILLS:
        raise AuditError("No Markdown skills selected, or selection exceeds file limit")
    result = []
    size = 0
    for path in sorted(files):
        text = read_text(path)
        size += len(text.encode("utf-8"))
        if size > MAX_TOTAL:
            raise AuditError("Selected Markdown contents exceed 10 MB")
        result.append({"path": str(path), "sha256": digest(text), "text": text})
    return result


def write_new(path: Path, text: str) -> None:
    path = no_links(path)
    try:
        # Never replace an earlier baseline, report, source file or skill by accident.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise AuditError(f"Cannot create new output {path}: {exc}") from exc


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_baseline(path: Path) -> dict:
    try:
        data = json.loads(read_text(path, 20_000_000), object_pairs_hook=_unique_object)
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("unknown baseline schema")
        if data.get("kind") != "skill_drift_snapshot" or data.get("reviewed") is not False:
            raise ValueError("not an unreviewed Skill Drift snapshot")
        if not isinstance(data["commit"], str) or not isinstance(data["repo"], str):
            raise ValueError("invalid repository identity")
        skills = data["skills"]
        if not isinstance(skills, list) or not 1 <= len(skills) <= MAX_SKILLS:
            raise ValueError("invalid skill set")
        seen = set()
        for skill in skills:
            if not all(isinstance(skill.get(k), str) for k in ("path", "text", "sha256")):
                raise ValueError("invalid skill entry")
            if skill["path"] in seen or digest(skill["text"]) != skill["sha256"]:
                raise ValueError("duplicate skill or content hash mismatch")
            seen.add(skill["path"])
        return data
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise AuditError(f"Invalid baseline: {exc}") from exc
