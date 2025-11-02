from __future__ import annotations

import json
import sqlite3

from catalog import ingest as catalog_ingest
from tests.helpers.catalog_builder import create_catalog_fixture, minimal_session_payload


def _metrics_payload() -> dict:
    first = minimal_session_payload(
        session_id="session-metrics",
        request_id="request-1",
        prompt="Run pytest -k broken",
        response="pytest failed",
    )
    first_request = first["requests"][0]
    first_request["timestamp"] = 1_697_200_000_000
    first_request["result"] = {
        "metadata": {
            "command": "pytest -k broken",
            "exitCode": 1,
            "messages": [
                {"role": "assistant", "content": "pytest -k broken exit code 1"},
            ],
        },
        "messages": [
            {"role": "assistant", "content": "pytest failed"},
        ],
    }

    second_request = {
        "requestId": "request-2",
        "timestamp": 1_697_200_100_000,
        "message": {
            "text": "Re-run pytest -k broken",
            "parts": [
                {
                    "kind": "text",
                    "text": "Re-run pytest -k broken",
                    "range": None,
                    "editorRange": None,
                }
            ],
        },
        "response": [
            {
                "value": "Still failing",
                "supportHtml": False,
                "supportThemeIcons": False,
            }
        ],
        "result": {
            "metadata": {
                "command": "pytest -k broken",
                "exitCode": 1,
            },
            "messages": [
                {"role": "assistant", "content": "Exit code 1"},
            ],
        },
        "followups": [],
        "isCanceled": False,
    }
    first["requests"].append(second_request)
    return first


def test_metrics_repeat_failures_populates_counts(tmp_path, monkeypatch):
    fixture = create_catalog_fixture(tmp_path, sessions=[_metrics_payload()])
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
        row = conn.execute(
            "SELECT workspace_fingerprint, command_hash, exit_code, occurrence_count, request_id, sample_snippet, redacted_payload_json"
            " FROM metrics_repeat_failures"
        ).fetchone()
        assert row is not None
        workspace_fingerprint = catalog_ingest.compute_workspace_fingerprint(fixture.workspace_root)
        assert row[0] == workspace_fingerprint
        assert row[2] == 1
        assert row[3] == 2
        assert row[4] == "request-2"
        assert row[5] and "pytest" in row[5]
        assert row[6] is not None
    finally:
        conn.close()

    manifest = json.loads(fixture.manifest_path.read_text(encoding="utf-8"))
    assert any(table["name"] == "metrics_repeat_failures" for table in manifest["tables"])
