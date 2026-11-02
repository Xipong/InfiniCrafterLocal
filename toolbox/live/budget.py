"""Explicit opt-in, durable item-attempt admission; never refunds failed attempts.

A recovery opening debit records known prior consumption without inventing lost
attempts. Call reserve_attempt *before* any provider work. A duplicate ID refuses
admission even after restart: an existing reservation is not permission to retry.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BudgetExhausted(RuntimeError):
    """The durable item-attempt ceiling has been reached."""


def _connect(path: Path, *, create: bool = False) -> sqlite3.Connection:
    mode = 'rwc' if create else 'rw'
    connection = sqlite3.connect(f'{path.resolve().as_uri()}?mode={mode}', uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA synchronous=FULL')
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_budget(
    path: Path, *, ceiling: int, opening_debit: int, opening_note: str,
) -> dict[str, Any]:
    """Create a policy once; reopening must present exactly the same policy."""
    if type(ceiling) is not int or type(opening_debit) is not int:
        raise ValueError('ceiling and opening_debit must be integers')
    if ceiling < 1 or not 0 <= opening_debit <= ceiling or not opening_note.strip():
        raise ValueError('invalid budget policy or missing opening provenance')
    with closing(_connect(path, create=True)) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('''CREATE TABLE IF NOT EXISTS policy (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            ceiling INTEGER NOT NULL CHECK(ceiling>0),
            opening_debit INTEGER NOT NULL CHECK(opening_debit>=0 AND opening_debit<=ceiling),
            opening_note TEXT NOT NULL, created_at TEXT NOT NULL)''')
        connection.execute('''CREATE TABLE IF NOT EXISTS attempts (
            attempt_id TEXT PRIMARY KEY, case_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('full_craft','stage_only')),
            reserved_at TEXT NOT NULL, finished_at TEXT, receipt_json TEXT)''')
        prior = connection.execute('SELECT * FROM policy WHERE singleton=1').fetchone()
        policy = (ceiling, opening_debit, opening_note)
        if prior is None:
            connection.execute('INSERT INTO policy VALUES (1,?,?,?,?)', (*policy, _now()))
        elif tuple(prior[key] for key in ('ceiling', 'opening_debit', 'opening_note')) != policy:
            raise ValueError('existing budget policy cannot be changed')
        return _status(connection)


def _status(connection: sqlite3.Connection) -> dict[str, Any]:
    policy = connection.execute('SELECT * FROM policy WHERE singleton=1').fetchone()
    if policy is None:
        raise ValueError('budget has not been initialized')
    attempts, active = connection.execute(
        'SELECT count(*), count(*) FILTER (WHERE finished_at IS NULL) FROM attempts'
    ).fetchone()
    charged = policy['opening_debit'] + attempts
    return {
        'ceiling': policy['ceiling'], 'openingDebit': policy['opening_debit'],
        'openingNote': policy['opening_note'], 'newAttempts': attempts,
        'active': active, 'charged': charged, 'remaining': policy['ceiling'] - charged,
    }


def budget_status(path: Path) -> dict[str, Any]:
    """Read an existing ledger; a missing file is not a new empty budget."""
    with closing(_connect(path)) as connection:
        return _status(connection)


def reserve_attempt(
    path: Path, *, attempt_id: str, case_id: str, kind: str,
) -> dict[str, Any]:
    """Atomically charge one full craft or stage-only variant before execution."""
    if not attempt_id.strip() or not case_id.strip() or kind not in ('full_craft', 'stage_only'):
        raise ValueError('nonempty attempt/case identity and explicit attempt kind are required')
    with closing(_connect(path)) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute('SELECT 1 FROM attempts WHERE attempt_id=?', (attempt_id,)).fetchone():
            raise ValueError('attempt already reserved; do not execute it again')
        if _status(connection)['remaining'] <= 0:
            raise BudgetExhausted('item-attempt budget exhausted')
        connection.execute(
            'INSERT INTO attempts(attempt_id,case_id,kind,reserved_at) VALUES (?,?,?,?)',
            (attempt_id, case_id, kind, _now()),
        )
        return {'attemptId': attempt_id, **_status(connection)}


def finish_attempt(path: Path, *, attempt_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
    """Attach an immutable terminal receipt; success/failure both remain charged."""
    if not isinstance(receipt, dict) or not receipt:
        raise ValueError('a nonempty terminal receipt is required')
    encoded = json.dumps(receipt, sort_keys=True, ensure_ascii=False, allow_nan=False)
    with closing(_connect(path)) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT * FROM attempts WHERE attempt_id=?', (attempt_id,)).fetchone()
        if row is None:
            raise ValueError('cannot finish an unreserved attempt')
        if row['finished_at'] is not None:
            if row['receipt_json'] != encoded:
                raise ValueError('terminal receipt cannot be changed')
        else:
            connection.execute(
                'UPDATE attempts SET finished_at=?,receipt_json=? WHERE attempt_id=?',
                (_now(), encoded, attempt_id),
            )
        return _status(connection)
