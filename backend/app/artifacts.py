"""Artifact persistence with content hashes for auditability."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from . import repository

TYPE_BY_SUFFIX = {
    ".png": "screenshot",
    ".jpg": "screenshot",
    ".jpeg": "screenshot",
    ".zip": "trace",
    ".json": "console_log",
    ".xml": "junit_report",
    ".txt": "log",
    ".log": "log",
    ".diff": "patch",
}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_file(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    path: Path,
    label: str,
    test_case_id: str | None = None,
    bug_id: str | None = None,
    artifact_type: str | None = None,
) -> dict:
    resolved = path.resolve()
    artifact_type = artifact_type or TYPE_BY_SUFFIX.get(resolved.suffix.lower(), "file")
    return repository.create_artifact(
        conn,
        run_id=run_id,
        artifact_type=artifact_type,
        label=label,
        storage_path=str(resolved),
        sha256=sha256_of(resolved),
        size_bytes=resolved.stat().st_size,
        test_case_id=test_case_id,
        bug_id=bug_id,
    )