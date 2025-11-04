from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TerminalCatalog:
    workspace_root: Path
    other_workspace: Path
    db_path: Path
    workspace_fingerprint: str
    other_fingerprint: str


def compute_fingerprint(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:16]


def build_terminal_catalog(tmp_path: Path) -> TerminalCatalog:
    workspace = tmp_path / "workspace"
    other_workspace = tmp_path / "other"
    workspace.mkdir()
    other_workspace.mkdir()

    db_path = workspace / ".vscode" / "CopilotChatHistory" / "copilot_chat_logs.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    fp_local = compute_fingerprint(workspace)
    fp_other = compute_fingerprint(other_workspace)

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

    return TerminalCatalog(
        workspace_root=workspace,
        other_workspace=other_workspace,
        db_path=db_path,
        workspace_fingerprint=fp_local,
        other_fingerprint=fp_other,
    )
