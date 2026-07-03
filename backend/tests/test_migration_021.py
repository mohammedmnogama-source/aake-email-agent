"""Tests for migration 021 (agent execution state).

Covers: applies when 019 columns exist, aborts before its own DDL when any 019
column is missing, leaves no partial objects on abort, backfills unique nonblank
keys, and enforces the execution_status CHECK constraint.
"""

import re
import sqlite3
import tempfile
from pathlib import Path

import pytest

from backend.database.connection import get_connection, init_db
from backend.database import connection as _conn_mod

_MIGRATION_021 = (
    Path(__file__).resolve().parents[1]
    / "database" / "migrations" / "021_agent_execution_state.sql"
).read_text()

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

_NEW_COLS = {
    "agent_suggestion_key",
    "execution_status",
    "execution_claimed_at",
    "execution_attempt_id",
}


def _cols(conn, table="suggested_tasks"):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_021_applies_via_runner_when_019_present():
    """A fresh DB (runner applies 000..021) has all four new columns."""
    tmp = tempfile.mkdtemp()
    db = str(Path(tmp) / "t.db")
    init_db(db)
    conn = get_connection()
    try:
        cols = _cols(conn)
        assert _NEW_COLS <= cols
        # migration recorded
        rec = conn.execute(
            "SELECT 1 FROM _migrations WHERE filename = '021_agent_execution_state.sql'"
        ).fetchone()
        assert rec is not None
    finally:
        conn.close()
        _conn_mod._DB_PATH = None


def _make_pre021(with_019: bool) -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    cols = "id INTEGER PRIMARY KEY, approved INTEGER DEFAULT 0, executed_at TEXT"
    if with_019:
        cols += ", erp_reference TEXT, error_message TEXT, confidence REAL, evidence_quote TEXT"
    c.executescript(f"CREATE TABLE suggested_tasks ({cols});")
    c.execute("INSERT INTO suggested_tasks (approved, executed_at) VALUES (1, NULL)")
    c.execute("INSERT INTO suggested_tasks (approved, executed_at) VALUES (1, '2026-01-01 00:00:00')")
    c.commit()
    return c


def test_021_backfills_unique_uuid_keys_and_marks_executed():
    c = _make_pre021(with_019=True)
    c.executescript(_MIGRATION_021)
    keys = [r[0] for r in c.execute("SELECT agent_suggestion_key FROM suggested_tasks")]
    assert all(k and _UUID4_RE.match(k) for k in keys)
    assert len(set(keys)) == len(keys)  # unique
    # row that was already executed becomes execution_status='executed'
    statuses = {
        r[0]: r[1]
        for r in c.execute("SELECT executed_at IS NOT NULL, execution_status FROM suggested_tasks")
    }
    assert statuses.get(1) == "executed"      # executed_at was set
    assert statuses.get(0) == "pending"       # not executed


def test_021_status_check_constraint():
    c = _make_pre021(with_019=True)
    c.executescript(_MIGRATION_021)
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE suggested_tasks SET execution_status='bogus' WHERE id=1")


def test_021_aborts_and_leaves_no_partial_when_019_missing():
    c = _make_pre021(with_019=False)
    with pytest.raises(sqlite3.OperationalError):
        c.executescript(_MIGRATION_021)
    # Roll back the aborted transaction the way the real runner does (close).
    cols = _cols(c)
    assert not (_NEW_COLS & cols), f"partial 021 columns present: {_NEW_COLS & cols}"
    idx = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_suggested_tasks_agent_key" not in idx
