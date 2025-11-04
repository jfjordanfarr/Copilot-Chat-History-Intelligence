from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from catalog import ingest as catalog_ingest
from tests.helpers.catalog_builder import create_catalog_fixture, minimal_session_payload, rich_session_payload


def test_catalog_ingest_populates_normalized_tables(tmp_path, monkeypatch):
    fixture = create_catalog_fixture(tmp_path, sessions=[rich_session_payload()])
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

        text_rows = conn.execute(
            "SELECT source_kind, output_index, tool_call_id, tool_name, plain_text FROM tool_output_text"
        ).fetchall()
        assert {row[0] for row in text_rows} >= {"tool_output", "tool_call_result"}
        assert any("pytest -k flaky_test" in (row[4] or "") for row in text_rows)

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
    assert {"requests", "tool_outputs", "tool_output_text", "metrics_repeat_failures"}.issubset(table_names)

    readme_path = fixture.catalog_path.parent / catalog_ingest.READ_ME_NAME
    assert readme_path.exists()

    audit_path = Path(fixture.workspace_root) / "AI-Agent-Workspace" / "_temp" / "ingest_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["sessions_ingested"] == 1
    assert audit["redaction_enabled"] is True
    assert audit["warnings"] == []


def test_catalog_ingest_skips_corrupt_files(tmp_path, monkeypatch):
    fixture = create_catalog_fixture(tmp_path, sessions=[minimal_session_payload()])
    monkeypatch.chdir(fixture.workspace_root)

    corrupt_path = fixture.source_dir / "corrupt.json"
    corrupt_path.write_text("{\"sessionId\": \"broken\"", encoding="utf-8")

    malformed_path = fixture.source_dir / "malformed.json"
    malformed_path.write_text("42", encoding="utf-8")

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

    conn = sqlite3.connect(fixture.catalog_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0] == 1
    finally:
        conn.close()

    audit_path = Path(fixture.workspace_root) / "AI-Agent-Workspace" / "_temp" / "ingest_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["sessions_ingested"] == 1
    assert len(audit["warnings"]) == 2
    assert any("corrupt.json" in warning and "invalid JSON" in warning for warning in audit["warnings"])
    assert any("malformed.json" in warning and "Unrecognized chat history format" in warning for warning in audit["warnings"])
