"""SQLite schema and connection helpers.

SQLite keeps the hackathon MVP auditable and restart-safe: every run, test,
bug, artifact and patch survives a backend restart.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    base_url    TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_runs (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status              TEXT NOT NULL,
    mode                TEXT NOT NULL DEFAULT 'reproduce',
    scope               TEXT NOT NULL DEFAULT '[]',
    max_duration_seconds INTEGER NOT NULL DEFAULT 120,
    plan                TEXT,
    summary             TEXT,
    error_kind          TEXT,
    error_message       TEXT,
    target_revision     TEXT,
    started_at          TEXT,
    finished_at         TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_project ON test_runs(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS test_cases (
    id              TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    test_key        TEXT NOT NULL,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL,
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    failure_message TEXT,
    attempt         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tests_run ON test_cases(run_id);

CREATE TABLE IF NOT EXISTS bugs (
    id                 TEXT PRIMARY KEY,
    run_id             TEXT NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    test_case_id       TEXT,
    title              TEXT NOT NULL,
    severity           TEXT NOT NULL,
    description        TEXT NOT NULL,
    root_cause         TEXT NOT NULL DEFAULT '',
    reproduction_steps TEXT NOT NULL DEFAULT '[]',
    status             TEXT NOT NULL DEFAULT 'confirmed',
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bugs_run ON bugs(run_id);

CREATE TABLE IF NOT EXISTS artifacts (
    id            TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    test_case_id  TEXT,
    bug_id        TEXT,
    type          TEXT NOT NULL,
    label         TEXT NOT NULL DEFAULT '',
    storage_path  TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id);

CREATE TABLE IF NOT EXISTS patches (
    id                  TEXT PRIMARY KEY,
    bug_id              TEXT NOT NULL REFERENCES bugs(id) ON DELETE CASCADE,
    summary             TEXT NOT NULL DEFAULT '',
    diff                TEXT NOT NULL,
    source              TEXT NOT NULL DEFAULT 'rule-based',
    status              TEXT NOT NULL DEFAULT 'proposed',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    verification_output TEXT,
    verification_tests  TEXT,
    revision            TEXT,
    created_at          TEXT NOT NULL,
    verified_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_patches_bug ON patches(bug_id);

CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_id      TEXT,
    summary     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id, created_at DESC);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


MIGRATIONS: dict[str, dict[str, str]] = {
    "patches": {"verification_tests": "TEXT"},
}


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database was first created."""
    for table, columns in MIGRATIONS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, ddl in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db(db_path: Path | str) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        _apply_migrations(conn)
        conn.commit()
    finally:
        conn.close()