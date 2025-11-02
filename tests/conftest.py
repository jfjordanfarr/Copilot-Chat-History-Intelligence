"""Shared pytest fixtures for the Copilot Recall Vision test suite."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import pytest


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture(scope="session")
def workspace_root() -> Path:
    """Return the repository root for locating fixtures and artifacts."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def catalog_workspace(workspace_root: Path) -> Path:
    """Ensure the catalog workspace directory exists for tests to target."""
    catalog_dir = workspace_root / ".vscode" / "CopilotChatHistory"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    return catalog_dir


@pytest.fixture()
def sample_catalog_path(tmp_path: Path, catalog_workspace: Path) -> Path:
    """Provide a writable SQLite catalog path for tests.

    If a real catalog already exists under the workspace, surface that path so
    integration tests can exercise full ingestion/export flows. Otherwise, create
    a temporary catalog in the pytest-provided tmp_path to keep tests isolated.
    """
    default_catalog = catalog_workspace / "copilot_chat_logs.db"
    if default_catalog.exists():
        return default_catalog
    temp_catalog = tmp_path / "copilot_chat_logs.db"
    temp_catalog.touch()
    return temp_catalog
