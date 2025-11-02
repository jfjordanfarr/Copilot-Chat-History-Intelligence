"""Utilities for constructing catalog fixtures in tests.

These helpers keep ingestion and export tests focused on behaviour rather than
boilerplate JSON assembly. They create realistic Copilot chat session payloads
and lay them out in the same folder structure VS Code uses on disk.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Sequence

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


@dataclass
class CatalogFixture:
    """Represents file-system artefacts required for catalog-driven tests."""

    workspace_root: Path
    source_dir: Path
    session_files: List[Path]
    catalog_path: Path
    manifest_path: Path
    readme_path: Path

    @property
    def catalog_dir(self) -> Path:
        return self.catalog_path.parent


def ensure_workspace_layout(workspace_root: Path) -> CatalogFixture:
    """Ensure the catalog workspace directory tree exists.

    This is useful for tests that only need the target paths without creating
    any raw session JSON. Callers that require session content should use
    :func:`create_catalog_fixture` instead.
    """

    catalog_dir = workspace_root / ".vscode" / "CopilotChatHistory"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    return CatalogFixture(
        workspace_root=workspace_root,
        source_dir=workspace_root / "AI-Agent-Workspace" / "Workspace-Helper-Scripts",
        session_files=[],
        catalog_path=catalog_dir / "copilot_chat_logs.db",
        manifest_path=catalog_dir / "schema_manifest.json",
        readme_path=workspace_root / "AI-Agent-Workspace" / "README_CopilotChatHistory.md",
    )


def create_catalog_fixture(
    tmp_path: Path,
    *,
    workspace_root: Optional[Path] = None,
    sessions: Optional[Sequence[Mapping[str, Any]]] = None,
    storage_parent: Optional[Path] = None,
) -> CatalogFixture:
    """Create a realistic Copilot storage tree with sample sessions.

    Parameters
    ----------
    tmp_path:
        Pytest-provided temporary directory used for synthetic storage.
    workspace_root:
        Optional workspace location; defaults to ``tmp_path / "workspace"``.
    sessions:
        Iterable of session payloads. When omitted, a minimal single-session
        payload is generated.
    storage_parent:
        Optional override for the VS Code global storage root.
    """

    workspace = workspace_root or tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    storage_root = storage_parent or tmp_path / "globalStorage"
    chat_session_dir = storage_root / "github.copilot-chat" / "chatSessions"
    chat_session_dir.mkdir(parents=True, exist_ok=True)

    session_payloads = list(sessions) if sessions else [minimal_session_payload()]
    written_sessions: List[Path] = []
    for payload in session_payloads:
        session_id = payload.get("sessionId") or f"session-{len(written_sessions)+1}"
        file_path = chat_session_dir / f"{session_id}.json"
        file_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        written_sessions.append(file_path)

    catalog_dir = workspace / ".vscode" / "CopilotChatHistory"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    ai_workspace = workspace / "AI-Agent-Workspace"
    ai_workspace.mkdir(exist_ok=True)

    return CatalogFixture(
        workspace_root=workspace,
        source_dir=chat_session_dir,
        session_files=written_sessions,
        catalog_path=catalog_dir / "copilot_chat_logs.db",
        manifest_path=catalog_dir / "schema_manifest.json",
        readme_path=ai_workspace / "README_CopilotChatHistory.md",
    )


def minimal_session_payload(
    *,
    session_id: str = "session-minimal",
    request_id: str = "request-minimal",
    prompt: str = "Show me failing pytest commands",
    response: str = "Re-run pytest -k flaky_test",
    created: Optional[datetime] = None,
) -> Mapping[str, Any]:
    """Generate a minimal but structurally faithful session payload."""

    created = created or datetime.now(timezone.utc)
    created_ms = int(created.timestamp() * 1000)
    return {
        "version": 1,
        "sessionId": session_id,
        "initialLocation": "panel",
        "creationDate": created_ms,
        "lastMessageDate": created_ms,
        "requests": [
            {
                "requestId": request_id,
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
                    "messages": [
                        {"role": "assistant", "content": response},
                    ],
                },
                "followups": [],
                "isCanceled": False,
                "timestamp": created_ms,
            }
        ],
    }


def load_session_json(path: Path) -> Mapping[str, Any]:
    """Convenience helper for tests that need to inspect written sessions."""

    return json.loads(path.read_text(encoding="utf-8"))


def iter_session_paths(fixture: CatalogFixture) -> Iterable[Path]:
    """Yield session JSON paths in deterministic order."""

    return tuple(sorted(fixture.session_files))
