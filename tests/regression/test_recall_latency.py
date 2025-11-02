from __future__ import annotations

from datetime import datetime, timezone

from catalog import ingest as catalog_ingest
from recall import conversation_recall
from tests.helpers.catalog_builder import CatalogFixture, create_catalog_fixture


def _latency_session_payload(index: int) -> dict:
    created = datetime(2025, 10, 23, 12, 0 + index, tzinfo=timezone.utc)
    timestamp_ms = int(created.timestamp() * 1000)
    command = f"pytest --maxfail=1 autosummarization {index}"
    return {
        "version": 1,
        "sessionId": f"latency-session-{index}",
        "initialLocation": "panel",
        "creationDate": timestamp_ms,
        "lastMessageDate": timestamp_ms,
        "requests": [
            {
                "requestId": f"latency-request-{index}",
                "timestamp": timestamp_ms,
                "message": {
                    "text": f"Autosummarization regression query {index}",
                    "parts": [
                        {
                            "kind": "text",
                            "text": f"Autosummarization regression query {index}",
                            "range": None,
                            "editorRange": None,
                        }
                    ],
                },
                "response": [
                    {
                        "value": "Try rerunning pytest with warmed cache",
                        "supportThemeIcons": False,
                        "supportHtml": False,
                    }
                ],
                "result": {
                    "metadata": {
                        "command": command,
                        "exitCode": 1,
                        "codeBlocks": [
                            {
                                "language": "bash",
                                "value": command,
                            }
                        ],
                    },
                    "messages": [
                        {
                            "role": "assistant",
                            "content": "Try rerunning pytest with warmed cache",
                        }
                    ],
                },
                "toolOutputs": [
                    {
                        "kind": "terminal",
                        "payload": {
                            "command": command,
                            "exitCode": 1,
                            "stderr": "Timeout",
                        },
                    }
                ],
                "agent": {
                    "id": "agent-latency",
                    "name": "Latency Agent",
                },
            }
        ],
    }


def _ingest_latency_fixture(tmp_path, monkeypatch) -> CatalogFixture:
    fixture = create_catalog_fixture(
        tmp_path,
        sessions=[_latency_session_payload(idx) for idx in range(3)],
    )
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
    return fixture


def test_recall_latency_stays_under_threshold(tmp_path, monkeypatch):
    fixture = _ingest_latency_fixture(tmp_path, monkeypatch)
    query = "autosummarization regression"

    # Warm cache and collect baseline results.
    initial_results, initial_elapsed = conversation_recall.query_catalog(
        query,
        db_path=fixture.catalog_path,
        limit=5,
        workspace_root=fixture.workspace_root,
    )
    assert initial_results
    assert initial_elapsed < 1.0

    cached_results, cached_elapsed = conversation_recall.query_catalog(
        query,
        db_path=fixture.catalog_path,
        limit=5,
        workspace_root=fixture.workspace_root,
    )
    assert cached_results
    assert cached_elapsed < 0.5, "Cached recall queries should complete well under the 2s SLA"

    cache_dir = fixture.workspace_root / "AI-Agent-Workspace" / ".cache" / "conversation_recall"
    cache_files = list(cache_dir.glob("*.pkl"))
    assert cache_files, "Expected cache artefacts to confirm warm-cache measurements"
