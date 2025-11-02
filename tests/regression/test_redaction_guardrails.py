from __future__ import annotations

import json
import sqlite3

from catalog import ingest as catalog_ingest
from tests.helpers.catalog_builder import create_catalog_fixture, minimal_session_payload


SECRET = "token=superSecretValue12345"


def _secret_session() -> dict:
    payload = minimal_session_payload(
        session_id="session-secret",
        request_id="request-secret",
        prompt=f"Please fix {SECRET}",
        response=f"Command failed with {SECRET}",
    )
    request = payload["requests"][0]
    request["timestamp"] = 1_697_100_000_000
    request["result"] = {
        "metadata": {"exitCode": 127, "command": f"echo {SECRET}"},
        "messages": [
            {"role": "assistant", "content": f"Exit due to {SECRET}"},
        ],
    }
    return payload


def test_redaction_guardrails_strip_secrets(tmp_path, monkeypatch):
    fixture = create_catalog_fixture(tmp_path, sessions=[_secret_session()])
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

    conn = sqlite3.connect(fixture.catalog_path)
    try:
        for table, column in (
            ("requests", "prompt_text"),
            ("responses", "value"),
            ("chat_sessions", "raw_json"),
            ("result_messages", "content"),
        ):
            rows = conn.execute(f"SELECT {column} FROM {table}").fetchall()
            assert rows
            for (value,) in rows:
                assert SECRET not in (value or "")
    finally:
        conn.close()

    manifest_text = fixture.manifest_path.read_text(encoding="utf-8")
    readme_text = (fixture.catalog_path.parent / catalog_ingest.READ_ME_NAME).read_text(encoding="utf-8")
    assert SECRET not in manifest_text
    assert SECRET not in readme_text

    audit_path = fixture.workspace_root / "AI-Agent-Workspace" / "_temp" / "ingest_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["redaction_enabled"] is True
    assert audit["secrets_redacted"] >= 1
