"""Persistence helpers. Every read decodes JSON columns into Python values."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .db import connect

JSON_COLUMNS = {
    "scope",
    "plan",
    "summary",
    "reproduction_steps",
    "verification_tests",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def session(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for column in JSON_COLUMNS & data.keys():
        if data[column] is not None:
            try:
                data[column] = json.loads(data[column])
            except (TypeError, json.JSONDecodeError):
                pass
    return data


def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [_row_to_dict(row) or {} for row in rows]


# --------------------------------------------------------------------------- projects
def create_project(
    conn: sqlite3.Connection, *, name: str, base_url: str, description: str = ""
) -> dict[str, Any]:
    project = {
        "id": new_id(),
        "name": name,
        "base_url": base_url,
        "description": description,
        "created_at": utc_now(),
    }
    conn.execute(
        "INSERT INTO projects (id, name, base_url, description, created_at)"
        " VALUES (:id, :name, :base_url, :description, :created_at)",
        project,
    )
    return project


def list_projects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return _rows(conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall())


def get_project(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    return _row_to_dict(
        conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    )


# --------------------------------------------------------------------------- runs
def create_run(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    scope: list[str],
    mode: str,
    max_duration_seconds: int = 120,
    target_revision: str | None = None,
) -> dict[str, Any]:
    run = {
        "id": new_id(),
        "project_id": project_id,
        "status": "queued",
        "mode": mode,
        "scope": json.dumps(scope),
        "max_duration_seconds": max_duration_seconds,
        "plan": None,
        "summary": None,
        "error_kind": None,
        "error_message": None,
        "target_revision": target_revision,
        "started_at": None,
        "finished_at": None,
        "created_at": utc_now(),
    }
    conn.execute(
        """INSERT INTO test_runs
           (id, project_id, status, mode, scope, max_duration_seconds, plan, summary,
            error_kind, error_message, target_revision, started_at, finished_at, created_at)
           VALUES (:id, :project_id, :status, :mode, :scope, :max_duration_seconds, :plan,
                   :summary, :error_kind, :error_message, :target_revision, :started_at,
                   :finished_at, :created_at)""",
        run,
    )
    return _row_to_dict(
        conn.execute("SELECT * FROM test_runs WHERE id = ?", (run["id"],)).fetchone()
    ) or run


def update_run(conn: sqlite3.Connection, run_id: str, **fields: Any) -> None:
    if not fields:
        return
    values = {
        key: json.dumps(value) if key in {"scope", "plan", "summary"} and value is not None else value
        for key, value in fields.items()
    }
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    values["id"] = run_id
    conn.execute(f"UPDATE test_runs SET {assignments} WHERE id = :id", values)


def get_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    return _row_to_dict(
        conn.execute(
            """SELECT r.*, p.name AS project_name, p.base_url AS project_base_url
               FROM test_runs r JOIN projects p ON p.id = r.project_id
               WHERE r.id = ?""",
            (run_id,),
        ).fetchone()
    )


def list_runs(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            """SELECT r.*, p.name AS project_name, p.base_url AS project_base_url
               FROM test_runs r JOIN projects p ON p.id = r.project_id
               ORDER BY r.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    )


# --------------------------------------------------------------------------- test cases
def add_test_case(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    test_key: str,
    name: str,
    status: str,
    duration_ms: int = 0,
    failure_message: str | None = None,
    attempt: int = 1,
) -> dict[str, Any]:
    record = {
        "id": new_id(),
        "run_id": run_id,
        "test_key": test_key,
        "name": name,
        "status": status,
        "duration_ms": int(duration_ms),
        "failure_message": failure_message,
        "attempt": attempt,
        "created_at": utc_now(),
    }
    conn.execute(
        """INSERT INTO test_cases
           (id, run_id, test_key, name, status, duration_ms, failure_message, attempt, created_at)
           VALUES (:id, :run_id, :test_key, :name, :status, :duration_ms, :failure_message,
                   :attempt, :created_at)""",
        record,
    )
    return record


def list_tests(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            "SELECT * FROM test_cases WHERE run_id = ? ORDER BY attempt ASC, created_at ASC",
            (run_id,),
        ).fetchall()
    )


def get_test(conn: sqlite3.Connection, test_id: str) -> dict[str, Any] | None:
    return _row_to_dict(
        conn.execute("SELECT * FROM test_cases WHERE id = ?", (test_id,)).fetchone()
    )


# --------------------------------------------------------------------------- bugs
def create_bug(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    test_case_id: str | None,
    title: str,
    severity: str,
    description: str,
    root_cause: str = "",
    reproduction_steps: list[str] | None = None,
    status: str = "confirmed",
) -> dict[str, Any]:
    bug = {
        "id": new_id(),
        "run_id": run_id,
        "test_case_id": test_case_id,
        "title": title,
        "severity": severity,
        "description": description,
        "root_cause": root_cause,
        "reproduction_steps": json.dumps(reproduction_steps or []),
        "status": status,
        "created_at": utc_now(),
    }
    conn.execute(
        """INSERT INTO bugs
           (id, run_id, test_case_id, title, severity, description, root_cause,
            reproduction_steps, status, created_at)
           VALUES (:id, :run_id, :test_case_id, :title, :severity, :description, :root_cause,
                   :reproduction_steps, :status, :created_at)""",
        bug,
    )
    result = _row_to_dict(
        conn.execute("SELECT * FROM bugs WHERE id = ?", (bug["id"],)).fetchone()
    ) or bug
    return result


def get_bug(conn: sqlite3.Connection, bug_id: str) -> dict[str, Any] | None:
    return _row_to_dict(conn.execute("SELECT * FROM bugs WHERE id = ?", (bug_id,)).fetchone())


def list_bugs(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            "SELECT * FROM bugs WHERE run_id = ? ORDER BY created_at ASC", (run_id,)
        ).fetchall()
    )


# --------------------------------------------------------------------------- artifacts
def create_artifact(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    artifact_type: str,
    label: str,
    storage_path: str,
    sha256: str,
    size_bytes: int,
    test_case_id: str | None = None,
    bug_id: str | None = None,
) -> dict[str, Any]:
    artifact = {
        "id": new_id(),
        "run_id": run_id,
        "test_case_id": test_case_id,
        "bug_id": bug_id,
        "type": artifact_type,
        "label": label,
        "storage_path": storage_path,
        "sha256": sha256,
        "size_bytes": int(size_bytes),
        "created_at": utc_now(),
    }
    conn.execute(
        """INSERT INTO artifacts
           (id, run_id, test_case_id, bug_id, type, label, storage_path, sha256, size_bytes, created_at)
           VALUES (:id, :run_id, :test_case_id, :bug_id, :type, :label, :storage_path, :sha256,
                   :size_bytes, :created_at)""",
        artifact,
    )
    artifact["download_url"] = f"/api/artifacts/{artifact['id']}"
    return artifact


def attach_artifacts_to_bug(
    conn: sqlite3.Connection, artifact_ids: list[str], bug_id: str
) -> None:
    conn.executemany(
        "UPDATE artifacts SET bug_id = ? WHERE id = ?",
        [(bug_id, artifact_id) for artifact_id in artifact_ids],
    )


def list_artifacts(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at ASC", (run_id,)
        ).fetchall()
    )


def get_artifact(conn: sqlite3.Connection, artifact_id: str) -> dict[str, Any] | None:
    return _row_to_dict(
        conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
    )


# --------------------------------------------------------------------------- patches
def create_patch(
    conn: sqlite3.Connection,
    *,
    bug_id: str,
    diff: str,
    summary: str = "",
    source: str = "rule-based",
    status: str = "proposed",
    verification_status: str = "unverified",
) -> dict[str, Any]:
    patch = {
        "id": new_id(),
        "bug_id": bug_id,
        "summary": summary,
        "diff": diff,
        "source": source,
        "status": status,
        "verification_status": verification_status,
        "verification_output": None,
        "verification_tests": None,
        "revision": None,
        "created_at": utc_now(),
        "verified_at": None,
    }
    conn.execute(
        """INSERT INTO patches
           (id, bug_id, summary, diff, source, status, verification_status, verification_output,
            verification_tests, revision, created_at, verified_at)
           VALUES (:id, :bug_id, :summary, :diff, :source, :status, :verification_status,
                   :verification_output, :verification_tests, :revision, :created_at, :verified_at)""",
        patch,
    )
    return patch


def get_patch(conn: sqlite3.Connection, patch_id: str) -> dict[str, Any] | None:
    return _row_to_dict(
        conn.execute("SELECT * FROM patches WHERE id = ?", (patch_id,)).fetchone()
    )


def update_patch(conn: sqlite3.Connection, patch_id: str, **fields: Any) -> None:
    if not fields:
        return
    values = {
        key: json.dumps(value) if key == "verification_tests" and value is not None else value
        for key, value in fields.items()
    }
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    values["id"] = patch_id
    conn.execute(f"UPDATE patches SET {assignments} WHERE id = :id", values)


def list_patches_for_bug(conn: sqlite3.Connection, bug_id: str) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            "SELECT * FROM patches WHERE bug_id = ? ORDER BY created_at DESC", (bug_id,)
        ).fetchall()
    )


# --------------------------------------------------------------------------- memories
def add_memory(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    summary: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    memory = {
        "id": new_id(),
        "project_id": project_id,
        "run_id": run_id,
        "summary": summary,
        "created_at": utc_now(),
    }
    conn.execute(
        "INSERT INTO memories (id, project_id, run_id, summary, created_at)"
        " VALUES (:id, :project_id, :run_id, :summary, :created_at)",
        memory,
    )
    return memory


def list_memories(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    return _rows(
        conn.execute(
            "SELECT * FROM memories WHERE project_id = ? ORDER BY created_at DESC LIMIT 20",
            (project_id,),
        ).fetchall()
    )