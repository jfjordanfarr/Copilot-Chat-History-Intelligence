from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from catalog import ingest as catalog_ingest
from recall import conversation_recall
from tests.helpers.catalog_builder import CatalogFixture, create_catalog_fixture

SESSION_ALPHA = "session-alpha"
SESSION_BETA = "session-beta"
REQUEST_ALPHA = "request-alpha"
REQUEST_BETA = "request-beta"
COMMAND_ALPHA = "pytest -k autosummarization"
COMMAND_BETA = "pytest --maxfail=1 autosummarization"
AGENT_ALPHA = "agent-alpha"
AGENT_BETA = "agent-beta"


def _session_payload(
    *,
    session_id: str,
    request_id: str,
    prompt: str,
    response: str,
    command: str,
    exit_code: int,
    agent_id: str,
    timestamp_ms: int,
) -> Mapping[str, object]:
    """Author a Copilot session payload with tool metadata for recall tests."""

    tool_payload = {
        "command": command,
        "exitCode": exit_code,
        "stderr": "Traceback (most recent call last)\nAssertionError",
    }

    return {
        "version": 1,
        "sessionId": session_id,
        "initialLocation": "panel",
        "creationDate": timestamp_ms,
        "lastMessageDate": timestamp_ms,
        "requests": [
            {
                "requestId": request_id,
                "timestamp": timestamp_ms,
                "message": {
                    "text": prompt,
                    "parts": [
                        {
                            "kind": "text",
                            "text": prompt,
                            "range": None,
                            "editorRange": None,
                        }
                    ],
                },
                "response": [
                    {
                        "value": response,
                        "supportThemeIcons": False,
                        "supportHtml": False,
                    }
                ],
                "result": {
                    "metadata": {
                        "command": command,
                        "exitCode": exit_code,
                        "toolCommand": command,
                        "messages": [
                            {
                                "role": "assistant",
                                "content": response,
                            }
                        ],
                        "codeBlocks": [
                            {
                                "language": "bash",
                                "value": command,
                            }
                        ],
                        "terminal": tool_payload,
                    },
                    "messages": [
                        {
                            "role": "assistant",
                            "content": response,
                        }
                    ],
                    "codeBlocks": [
                        {
                            "language": "bash",
                            "value": command,
                        }
                    ],
                },
                "toolOutputs": [
                    {
                        "kind": "terminal",
                        "payload": tool_payload,
                    }
                ],
                "agent": {
                    "id": agent_id,
                    "name": agent_id.title(),
                },
                "followups": [],
                "isCanceled": False,
            }
        ],
    }


def _build_sessions() -> Iterable[Mapping[str, object]]:
    created = datetime(2025, 10, 22, 17, 45, tzinfo=timezone.utc)
    base_ms = int(created.timestamp() * 1000)
    yield _session_payload(
        session_id=SESSION_ALPHA,
        request_id=REQUEST_ALPHA,
        prompt="Autosummarization retries keep failing pytest",
        response="Re-run pytest -k autosummarization after fixing the tmp file",
        command=COMMAND_ALPHA,
        exit_code=1,
        agent_id=AGENT_ALPHA,
        timestamp_ms=base_ms,
    )
    yield _session_payload(
        session_id=SESSION_BETA,
        request_id=REQUEST_BETA,
        prompt="Autosummarization warm cache pytest guidance",
        response="Consider pytest --maxfail=1 autosummarization rerun",
        command=COMMAND_BETA,
        exit_code=2,
        agent_id=AGENT_BETA,
        timestamp_ms=base_ms + 1200,
    )


def _ingest_catalog(tmp_path: Path, monkeypatch) -> CatalogFixture:
    fixture = create_catalog_fixture(tmp_path, sessions=list(_build_sessions()))
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


def test_query_catalog_enriches_metadata_and_cache(tmp_path, monkeypatch):
    fixture = _ingest_catalog(tmp_path, monkeypatch)
    db_path = fixture.catalog_path
    workspace_root = fixture.workspace_root

    query = "pytest autosummarization failure"
    results, elapsed = conversation_recall.query_catalog(
        query,
        db_path=db_path,
        limit=5,
        workspace_root=workspace_root,
    )

    assert results, "Expected recall results for autosummarization query"
    assert elapsed >= 0

    documents = {document.request_id: document for _, document in results}
    assert REQUEST_ALPHA in documents
    alpha_doc = documents[REQUEST_ALPHA]
    assert alpha_doc.command_text == COMMAND_ALPHA
    assert alpha_doc.exit_code == 1
    assert alpha_doc.tool_summaries, "Tool outputs should surface in the document"
    assert any("terminal" in summary for summary in alpha_doc.tool_summaries)
    assert alpha_doc.timestamp_ms is not None

    fingerprint = conversation_recall.compute_workspace_fingerprint(workspace_root)
    assert alpha_doc.workspace_fingerprint == fingerprint

    formatted = conversation_recall.format_result(results[0][0], results[0][1])
    assert f"fingerprint={fingerprint}" in formatted
    assert "command=" in formatted
    assert "exit_code=" in formatted

    cache_dir = workspace_root / "AI-Agent-Workspace" / ".cache" / "conversation_recall"
    cache_files = list(cache_dir.glob("*.pkl"))
    assert cache_files, "Expected recall cache artefact to be created"

    repeat_results, repeat_elapsed = conversation_recall.query_catalog(
        query,
        db_path=db_path,
        limit=5,
        workspace_root=workspace_root,
    )
    assert repeat_results
    assert repeat_elapsed >= 0
    assert repeat_results[0][1].request_id in {REQUEST_ALPHA, REQUEST_BETA}


def test_query_catalog_respects_filters(tmp_path, monkeypatch):
    fixture = _ingest_catalog(tmp_path, monkeypatch)
    db_path = fixture.catalog_path
    workspace_root = fixture.workspace_root

    query = "pytest autosummarization"
    all_results, _ = conversation_recall.query_catalog(
        query,
        db_path=db_path,
        limit=5,
        workspace_root=workspace_root,
    )
    assert {doc.session_id for _, doc in all_results} == {SESSION_ALPHA, SESSION_BETA}

    session_filtered, _ = conversation_recall.query_catalog(
        query,
        db_path=db_path,
        limit=5,
        sessions=[SESSION_ALPHA],
        workspace_root=workspace_root,
    )
    assert session_filtered
    assert {doc.session_id for _, doc in session_filtered} == {SESSION_ALPHA}

    agent_filtered, _ = conversation_recall.query_catalog(
        query,
        db_path=db_path,
        limit=5,
        agent=AGENT_BETA,
        workspace_root=workspace_root,
    )
    assert agent_filtered
    assert {doc.agent_id for _, doc in agent_filtered} == {AGENT_BETA}

    fingerprint = conversation_recall.compute_workspace_fingerprint(workspace_root)
    workspace_filtered, _ = conversation_recall.query_catalog(
        query,
        db_path=db_path,
        limit=5,
        workspaces=[fingerprint],
        workspace_root=workspace_root,
    )
    assert workspace_filtered

    empty_results, empty_elapsed = conversation_recall.query_catalog(
        query,
        db_path=db_path,
        limit=5,
        workspaces=["deadbeef"],
        workspace_root=workspace_root,
    )
    assert empty_results == []
    assert empty_elapsed == 0.0
