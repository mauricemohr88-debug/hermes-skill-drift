"""Read committed Git objects without checkouts, filters, imports or lazy network fetches."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from .storage import MAX_FILE, AuditError

MAX_TREE = 15_000_000
MAX_SOURCE_TOTAL = 80_000_000


class GitSource:
    def __init__(self, path: str):
        self.path = str(Path(path).expanduser().resolve(strict=True))
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PAGER": "cat",
            }
        )
        self.prefix = [
            "git",
            "--no-pager",
            "--no-replace-objects",
            "-c",
            "core.fsmonitor=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "protocol.allow=never",
            "-C",
            self.path,
        ]
        self.run(["rev-parse", "--git-dir"])

    def run(self, args: list[str], limit: int = MAX_TREE, data: bytes | None = None) -> bytes:
        # Capture into temporary files, so an oversized repository cannot exhaust RAM.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            try:
                result = subprocess.run(
                    self.prefix + args,
                    env=self.env,
                    input=data,
                    stdout=output,
                    stderr=errors,
                    timeout=45,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise AuditError(f"Git read failed: {exc}") from exc
            if result.returncode:
                errors.seek(0)
                detail = errors.read(1500).decode("utf-8", errors="replace")
                raise AuditError(f"Git evidence unavailable: {detail.strip()}")
            if output.tell() > limit:
                raise AuditError("Git output exceeds the audit size limit")
            output.seek(0)
            return output.read()

    def resolve(self, ref: str) -> str:
        if not ref or ref.startswith("-") or any(ord(c) < 32 for c in ref):
            raise AuditError("Invalid Git revision")
        result = self.run(["rev-parse", "--verify", "--end-of-options", ref + "^{commit}"])
        commit = result.decode("ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            raise AuditError("Git did not resolve a full commit identity")
        return commit

    def tree(self, commit: str) -> dict[str, dict]:
        raw = self.run(["ls-tree", "-r", "-l", "-z", commit])
        result = {}
        for entry in raw.split(b"\0"):
            if not entry:
                continue
            head, name = entry.split(b"\t", 1)
            mode, kind, oid, size = head.split()
            try:
                path = name.decode("utf-8")
            except UnicodeError as exc:
                raise AuditError("Repository contains non-UTF-8 paths") from exc
            result[path] = {
                "mode": mode.decode(),
                "kind": kind.decode(),
                "oid": oid.decode(),
                # Partial clones can list an absent blob as BAD when lazy fetch is off.
                # Keep the path evidence, but never read it as an empty/valid source.
                "size": int(size) if size.isdigit() else None,
            }
        return result

    def texts(self, tree: dict, paths: list[str]) -> tuple[dict[str, str], list[str]]:
        selected = []
        warnings = []
        total = 0
        for path in paths:
            entry = tree[path]
            if entry["mode"] not in ("100644", "100755") or entry["kind"] != "blob":
                warnings.append(f"{path}: non-regular Git object not inspected")
                continue
            if entry["size"] is None:
                warnings.append(f"{path}: blob missing locally; no automatic fetch attempted")
                continue
            if entry["size"] > MAX_FILE:
                warnings.append(f"{path}: source exceeds 1 MB, not inspected")
                continue
            total += entry["size"]
            if total > MAX_SOURCE_TOTAL:
                raise AuditError("Selected committed source exceeds 80 MB")
            selected.append(path)
        if not selected:
            return {}, warnings
        raw = self.run(
            ["cat-file", "--batch"],
            limit=MAX_SOURCE_TOTAL + len(selected) * 150,
            data="".join(tree[p]["oid"] + "\n" for p in selected).encode("ascii"),
        )
        result = {}
        offset = 0
        for path in selected:
            end = raw.find(b"\n", offset)
            header = raw[offset:end].split()
            if len(header) != 3 or header[1] != b"blob":
                raise AuditError(f"Committed blob unavailable: {path}")
            size = int(header[2])
            if size != tree[path]["size"] or header[0].decode() != tree[path]["oid"]:
                raise AuditError(f"Committed blob size/identity mismatch: {path}")
            offset = end + 1
            blob = raw[offset : offset + size]
            offset += size + 1
            try:
                result[path] = blob.decode("utf-8")
            except UnicodeError:
                warnings.append(f"{path}: source not UTF-8, not inspected")
        return result, warnings
