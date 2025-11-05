from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from analysis import similarity_threshold


@pytest.fixture()
def metrics_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "metrics.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE metrics_repeat_failures (
                workspace_fingerprint TEXT NOT NULL,
                command_hash TEXT NOT NULL,
                command_text TEXT,
                exit_code INTEGER NOT NULL,
                occurrence_count INTEGER NOT NULL,
                last_seen_ms INTEGER,
                request_id TEXT,
                sample_snippet TEXT,
                redacted_payload_json TEXT,
                PRIMARY KEY (workspace_fingerprint, command_hash, exit_code)
            )
            """
        )
    return db_path


def _insert(conn: sqlite3.Connection, *, count: int, last_seen_ms: int | None) -> None:
    conn.execute(
        """
        INSERT INTO metrics_repeat_failures (
            workspace_fingerprint,
            command_hash,
            command_text,
            exit_code,
            occurrence_count,
            last_seen_ms
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("abcd1234efgh5678", f"hash-{count}-{last_seen_ms}", "pytest", 1, count, last_seen_ms),
    )


def test_similarity_threshold_uses_recent_window(metrics_db: Path, monkeypatch) -> None:
    with sqlite3.connect(metrics_db) as conn:
        _insert(conn, count=1, last_seen_ms=1_000)
        _insert(conn, count=4, last_seen_ms=200_000_000_0000)
        _insert(conn, count=6, last_seen_ms=200_000_100_0000)
        conn.commit()

    result = similarity_threshold.compute_similarity_threshold(
        metrics_db,
        percentile=0.9,
        window_days=30,
    )

    assert result.samples == 2
    assert not result.fallback_used
    assert 0.98 <= result.threshold <= 0.999


def test_similarity_threshold_falls_back_when_no_rows(metrics_db: Path) -> None:
    result = similarity_threshold.compute_similarity_threshold(metrics_db)
    assert result.fallback_used
    assert result.threshold == similarity_threshold.FALLBACK_THRESHOLD


def test_similarity_threshold_uses_all_data_when_window_empty(metrics_db: Path) -> None:
    with sqlite3.connect(metrics_db) as conn:
        _insert(conn, count=2, last_seen_ms=1_000)  # far outside window
        _insert(conn, count=3, last_seen_ms=2_000)
        conn.commit()

    result = similarity_threshold.compute_similarity_threshold(
        metrics_db,
        window_days=1,
    )
    assert result.samples == 2
    assert not result.fallback_used
    assert 0.86 <= result.threshold <= 0.95
