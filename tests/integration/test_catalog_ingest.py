from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from catalog import ingest as catalog_ingest
from tests.helpers.catalog_builder import create_catalog_fixture, minimal_session_payload


def _rich_session_payload() -> dict:
    payload = minimal_session_payload(
        session_id="session-rich",
        request_id="request-rich",
        prompt="Run pytest with detailed logs",
        response="Command finished with exit code 1",
    )
    request = payload["requests"][0]
    request["agent"] = {
        "id": "copilot-chat",
        "name": "GitHub Copilot",
        "isDefault": True,
        "locations": ["panel"],
    }
    request["timestamp"] = 1_697_000_000_000
    request["variableData"] = [
        {
            "id": "vscode.selection",
            "name": "Selection",
            "value": {"uri": "file:///tmp/example.py"},
            "isFile": False,
            "modelDescription": "Selected code",
        }
    ]
    request["result"] = {
        "timings": {"firstProgress": 250, "totalElapsed": 900},
        "metadata": {
            "codeBlocks": [
                {"language": "bash", "value": "pytest -k flaky_test"},
            ],
            "messages": [
                {"role": "assistant", "content": "pytest -k flaky_test failed with exit code 1"}
            ],
            "toolInvocations": [
                {
                    "name": "run_in_terminal",
                    "args": {"command": "pytest -k flaky_test"},
                    "result": {"exitCode": 1},
                }
            ],
        },
        "messages": [
            {"role": "assistant", "content": "Use pytest -k flaky_test"},
        ],
    }
    request["response"] = [
        {
            "value": "Command finished with exit code 1",
            "supportThemeIcons": False,
            "supportHtml": False,
        },
        {
            "kind": "toolInvocationSerialized",
            "toolSpecificData": {
                "commandLine": {"original": "pytest -k flaky_test"},
                "toolResult": {"exitCode": 1, "stderr": "FAILED tests/test_example.py"},
            },
        },
    ]
    request["toolOutputs"] = [
        {"kind": "terminal", "payload": {"exit_code": 1, "command": "pytest -k flaky_test"}}
    ]
    return payload


def test_catalog_ingest_populates_normalized_tables(tmp_path, monkeypatch):
    fixture = create_catalog_fixture(tmp_path, sessions=[_rich_session_payload()])
    monkeypatch.chdir(fixture.workspace_root)

    catalog_ingest.main(
        [
            str(fixture.source_dir),
            "--db",
            str(fixture.catalog_path),
            "--output-dir",
            str(fixture.catalog_path.parent),
            "--workspace-root",
            str(fixture.workspace_root),
        ]
    )

    assert fixture.catalog_path.exists()
    conn = sqlite3.connect(fixture.catalog_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0] == 1
        request_row = conn.execute(
            "SELECT prompt_text, agent_id, timing_total_ms FROM requests"
        ).fetchone()
        assert request_row is not None
        assert "pytest" in (request_row[0] or "")
        assert request_row[1] == "copilot-chat"
        assert request_row[2] == 900

        part_count = conn.execute("SELECT COUNT(*) FROM request_parts").fetchone()[0]
        assert part_count == 1

        tool_rows = conn.execute("SELECT tool_kind, payload_json FROM tool_outputs").fetchall()
        assert tool_rows

        conn.execute("SELECT * FROM catalog_metadata WHERE key='schema_version'").fetchone()
        repeat_rows = conn.execute(
            "SELECT command_text, exit_code, occurrence_count FROM metrics_repeat_failures"
        ).fetchall()
        assert repeat_rows == [("pytest -k flaky_test", 1, 1)]
    finally:
        conn.close()

    manifest = json.loads(fixture.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == catalog_ingest.CATALOG_VERSION
    table_names = {table["name"] for table in manifest["tables"]}
    assert {"requests", "tool_outputs", "metrics_repeat_failures"}.issubset(table_names)

    readme_path = fixture.catalog_path.parent / catalog_ingest.READ_ME_NAME
    assert readme_path.exists()

    audit_path = Path(fixture.workspace_root) / "AI-Agent-Workspace" / "_temp" / "ingest_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["sessions_ingested"] == 1
    assert audit["redaction_enabled"] is True
    assert audit["warnings"] == []
