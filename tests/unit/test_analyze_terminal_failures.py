import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers.terminal_catalog import build_terminal_catalog, compute_fingerprint


@pytest.fixture()
def helper_script() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "AI-Agent-Workspace"
        / "Workspace-Helper-Scripts"
        / "analyze_terminal_failures.py"
    )


def test_default_scope_reports_local_commands(tmp_path: Path, helper_script: Path) -> None:
    catalog = build_terminal_catalog(tmp_path)
    workspace = catalog.workspace_root
    db_path = catalog.db_path

    cmd = [sys.executable, str(helper_script), "--db", str(db_path), "--limit", "5"]
    result = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    stdout = result.stdout
    assert "Terminal summary:" in stdout
    assert "total=2" in stdout
    assert "failure_rate=50.0%" in stdout
    assert "npm run lint" in stdout
    assert "npm run graph:audit" not in stdout  # filtered by workspace fingerprint


def test_output_json_with_samples(tmp_path: Path, helper_script: Path) -> None:
    catalog = build_terminal_catalog(tmp_path)
    workspace = catalog.workspace_root
    db_path = catalog.db_path

    output_path = workspace / "terminal_report.json"
    cmd = [
        sys.executable,
        str(helper_script),
        "--db",
        str(db_path),
        "--limit",
        "5",
        "--output",
        str(output_path),
        "--sample-limit",
        "1",
        "--all-workspaces",
    ]
    result = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    stdout = result.stdout
    assert "Wrote report to" in stdout

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["workspace_filters"] is None
    assert payload["summary"]["total_calls"] == 3
    commands = payload["commands"]
    assert {entry["command"] for entry in commands} == {"npm run lint", "npm run graph:audit"}
    lint_entry = next(entry for entry in commands if entry["command"] == "npm run lint")
    assert lint_entry["failure_rate"] == pytest.approx(0.5)
    samples = lint_entry.get("samples")
    assert samples is not None
    assert len(samples) == 1
    sample = samples[0]
    assert sample["workspace_fingerprint"] == compute_fingerprint(workspace)
    assert "transcript" in sample and "Exit code" in sample["transcript"]
