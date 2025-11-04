import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


def compute_fingerprint(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:16]


@pytest.fixture()
def helper_script() -> Path:
    return Path(__file__).resolve().parents[2] / "AI-Agent-Workspace" / "Workspace-Helper-Scripts" / "measure_repeat_failures.py"


def prepare_catalog(workspace: Path, other_workspace: Path) -> Path:
    db_path = workspace / ".vscode" / "CopilotChatHistory" / "copilot_chat_logs.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
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
        fp_local = compute_fingerprint(workspace)
        fp_other = compute_fingerprint(other_workspace)
        conn.execute(
            """
            INSERT INTO metrics_repeat_failures(
                workspace_fingerprint,
                command_hash,
                command_text,
                exit_code,
                occurrence_count,
                last_seen_ms,
                request_id,
                sample_snippet,
                redacted_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (fp_local, "hash-local", "npm run lint", 1, 3, 1_000, "req-local", "npm run lint", None),
        )
        conn.execute(
            """
            INSERT INTO metrics_repeat_failures(
                workspace_fingerprint,
                command_hash,
                command_text,
                exit_code,
                occurrence_count,
                last_seen_ms,
                request_id,
                sample_snippet,
                redacted_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (fp_other, "hash-other", "npm run graph:audit", 3, 5, 2_000, "req-other", "npm run graph:audit", None),
        )

        metadata_local_fail = {
            "toolCallRounds": [
                {
                    "toolCalls": [
                        {
                            "id": "call-local-fail",
                            "name": "run_in_terminal",
                            "arguments": json.dumps({"command": "npm run lint"}),
                        }
                    ]
                }
            ],
            "toolCallResults": {
                "call-local-fail": {
                    "content": [
                        {"value": "npm ERR! command failed\nExit code: 1"}
                    ]
                }
            },
        }
        metadata_local_success = {
            "toolCallRounds": [
                {
                    "toolCalls": [
                        {
                            "id": "call-local-success",
                            "name": "run_in_terminal",
                            "arguments": json.dumps({"command": "npm run lint"}),
                        }
                    ]
                }
            ],
            "toolCallResults": {
                "call-local-success": {
                    "content": [
                        {"value": "All tests passed\nExit code: 0"}
                    ]
                }
            },
        }
        metadata_other_fail = {
            "toolCallRounds": [
                {
                    "toolCalls": [
                        {
                            "id": "call-other-fail",
                            "name": "run_in_terminal",
                            "arguments": json.dumps({"command": "npm run graph:audit"}),
                        }
                    ]
                }
            ],
            "toolCallResults": {
                "call-other-fail": {
                    "content": [
                        {"value": "Command failed\nExit code: 3"}
                    ]
                }
            },
        }

        conn.execute(
            "INSERT INTO requests VALUES (?, ?, ?, ?)",
            ("req-local", fp_local, 1_000, json.dumps(metadata_local_fail)),
        )
        conn.execute(
            "INSERT INTO requests VALUES (?, ?, ?, ?)",
            ("req-local-2", fp_local, 1_500, json.dumps(metadata_local_success)),
        )
        conn.execute(
            "INSERT INTO requests VALUES (?, ?, ?, ?)",
            ("req-other", fp_other, 2_000, json.dumps(metadata_other_fail)),
        )
        conn.executemany(
            "INSERT INTO tool_output_text (request_id, tool_call_id, tool_name, plain_text) VALUES (?, ?, ?, ?)",
            [
                ("req-local", "call-local-fail", "run_in_terminal", "npm ERR! command failed\nExit code: 1"),
                ("req-local-2", "call-local-success", "run_in_terminal", "All tests passed\nExit code: 0"),
                ("req-other", "call-other-fail", "run_in_terminal", "Command failed\nExit code: 3"),
            ],
        )
    return db_path


def load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_workspace_filter_defaults(tmp_path: Path, helper_script: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    other_workspace = tmp_path / "other"
    other_workspace.mkdir()
    db_path = prepare_catalog(workspace, other_workspace)

    output_path = workspace / "report.json"
    cmd = [sys.executable, str(helper_script), "--db", str(db_path), "--output", str(output_path)]
    result = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    report = load_report(output_path)
    entries = report["entries"]
    assert len(entries) == 1
    assert entries[0]["workspace_fingerprint"] == compute_fingerprint(workspace)
    assert report["workspace_filters"] == [compute_fingerprint(workspace)]
    terminal_metrics = report.get("terminal_failure_analysis")
    assert terminal_metrics is not None
    summary = terminal_metrics["summary"]
    assert summary["total_calls"] == 2
    assert summary["failures"] == 1
    assert summary["successes"] == 1
    top_commands = terminal_metrics["top_commands"]
    assert any(item["command"] == "npm run lint" and item["failure_rate"] == pytest.approx(0.5) for item in top_commands)


def test_all_workspaces_bypass_filter(tmp_path: Path, helper_script: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    other_workspace = tmp_path / "other"
    other_workspace.mkdir()
    db_path = prepare_catalog(workspace, other_workspace)

    output_path = workspace / "report_all.json"
    cmd = [
        sys.executable,
        str(helper_script),
        "--db",
        str(db_path),
        "--output",
        str(output_path),
        "--all-workspaces",
    ]
    result = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    report = load_report(output_path)
    fingerprints = {entry["workspace_fingerprint"] for entry in report["entries"]}
    assert fingerprints == {
        compute_fingerprint(workspace),
        compute_fingerprint(other_workspace),
    }
    assert report["workspace_filters"] is None


def test_explicit_workspace_selectors(tmp_path: Path, helper_script: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    other_workspace = tmp_path / "other"
    other_workspace.mkdir()
    db_path = prepare_catalog(workspace, other_workspace)

    output_path = workspace / "report_selected.json"
    cmd = [
        sys.executable,
        str(helper_script),
        "--db",
        str(db_path),
        "--output",
        str(output_path),
        "--workspace",
        ".",
        "--workspace",
        str(other_workspace),
    ]
    result = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    report = load_report(output_path)
    fingerprints = {entry["workspace_fingerprint"] for entry in report["entries"]}
    assert fingerprints == {
        compute_fingerprint(workspace),
        compute_fingerprint(other_workspace),
    }
    assert sorted(report["workspace_filters"]) == sorted(
        [compute_fingerprint(workspace), compute_fingerprint(other_workspace)]
    )
