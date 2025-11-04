from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from analysis import terminal_failures as tf


@pytest.fixture(name="sample_db")
def sample_db_fixture(tmp_path: Path) -> Path:
    db_path = tmp_path / "catalog.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE requests (
                request_id TEXT PRIMARY KEY,
                workspace_fingerprint TEXT,
                timestamp_ms INTEGER,
                result_metadata_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE tool_output_text (
                fragment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT,
                tool_call_id TEXT,
                tool_name TEXT,
                plain_text TEXT
            )
            """
        )

        success_metadata = {
            "toolCallRounds": [
                {
                    "toolCalls": [
                        {
                            "id": "call-success",
                            "name": "run_in_terminal",
                            "arguments": json.dumps({"command": "echo success"}),
                        }
                    ]
                }
            ],
            "toolCallResults": {
                "call-success": {
                    "content": [
                        {"value": "All tests passed\nExit code: 0"}
                    ]
                }
            },
        }
        failure_metadata = {
            "toolCallRounds": [
                {
                    "toolCalls": [
                        {
                            "id": "call-failure",
                            "name": "run_in_terminal",
                            "arguments": json.dumps({"command": "npm run lint"}),
                        }
                    ]
                }
            ],
            "toolCallResults": {
                "call-failure": {
                    "content": [
                        {"value": "npm ERR! command failed\nExit code: 1"}
                    ]
                }
            },
        }
        conn.execute(
            "INSERT INTO requests VALUES (?, ?, ?, ?)",
            (
                "req-success",
                "fingerprint",
                1,
                json.dumps(success_metadata),
            ),
        )
        conn.execute(
            "INSERT INTO requests VALUES (?, ?, ?, ?)",
            (
                "req-failure",
                "fingerprint",
                2,
                json.dumps(failure_metadata),
            ),
        )
        conn.executemany(
            "INSERT INTO tool_output_text (request_id, tool_call_id, tool_name, plain_text) VALUES (?, ?, ?, ?)",
            [
                ("req-success", "call-success", "run_in_terminal", "All tests passed\nExit code: 0"),
                ("req-failure", "call-failure", "run_in_terminal", "npm ERR! command failed\nExit code: 1"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_load_terminal_calls_extracts_commands(sample_db: Path) -> None:
    calls = tf.load_terminal_calls(sample_db)
    assert len(calls) == 2
    commands = {call.command for call in calls}
    assert "echo success" in commands
    assert "npm run lint" in commands
    success_call = next(call for call in calls if call.command == "echo success")
    assert success_call.exit_code == 0
    failure_call = next(call for call in calls if call.command == "npm run lint")
    assert failure_call.exit_code == 1


def test_classification_uses_exit_code(sample_db: Path) -> None:
    calls = tf.load_terminal_calls(sample_db)
    statuses = {call.command: tf.classify_terminal_call(call) for call in calls}
    assert statuses["echo success"] == "success"
    assert statuses["npm run lint"] == "failure"


def test_aggregate_command_stats_counts(sample_db: Path) -> None:
    calls = tf.load_terminal_calls(sample_db)
    stats = tf.aggregate_command_stats(calls)
    index = {item.command: item for item in stats}
    assert index["echo success"].successes == 1
    assert index["echo success"].failures == 0
    assert index["npm run lint"].failures == 1
    assert index["npm run lint"].failure_rate == pytest.approx(1.0)


def test_summarise_overall_reports_breakdown(sample_db: Path) -> None:
    calls = tf.load_terminal_calls(sample_db)
    summary = tf.summarise_overall(calls)
    assert summary["total_calls"] == 2
    assert summary["successes"] == 1
    assert summary["failures"] == 1
    assert summary["failure_rate"] == pytest.approx(0.5)
