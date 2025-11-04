import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.helpers.terminal_catalog import build_terminal_catalog, compute_fingerprint

@pytest.fixture()
def helper_script() -> Path:
    return Path(__file__).resolve().parents[2] / "AI-Agent-Workspace" / "Workspace-Helper-Scripts" / "measure_repeat_failures.py"


def load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_workspace_filter_defaults(tmp_path: Path, helper_script: Path) -> None:
    catalog = build_terminal_catalog(tmp_path)
    workspace = catalog.workspace_root
    db_path = catalog.db_path

    output_path = workspace / "report.json"
    cmd = [sys.executable, str(helper_script), "--db", str(db_path), "--output", str(output_path)]
    result = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    report = load_report(output_path)
    entries = report["entries"]
    assert len(entries) == 1
    assert entries[0]["workspace_fingerprint"] == compute_fingerprint(workspace)
    assert report["workspace_filters"] == [compute_fingerprint(workspace)]
    terminal_metrics = report.get("terminal_failure_analysis")
    assert terminal_metrics is not None
    summary = terminal_metrics["summary"]
    assert summary["total_calls"] == 2
    assert summary["failures"] == 1
    assert summary["successes"] == 1
    top_commands = terminal_metrics["top_commands"]
    assert any(item["command"] == "npm run lint" and item["failure_rate"] == pytest.approx(0.5) for item in top_commands)


def test_all_workspaces_bypass_filter(tmp_path: Path, helper_script: Path) -> None:
    catalog = build_terminal_catalog(tmp_path)
    workspace = catalog.workspace_root
    other_workspace = catalog.other_workspace
    db_path = catalog.db_path

    output_path = workspace / "report_all.json"
    cmd = [
        sys.executable,
        str(helper_script),
        "--db",
        str(db_path),
        "--output",
        str(output_path),
        "--all-workspaces",
    ]
    result = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    report = load_report(output_path)
    fingerprints = {entry["workspace_fingerprint"] for entry in report["entries"]}
    assert fingerprints == {
        compute_fingerprint(workspace),
        compute_fingerprint(other_workspace),
    }
    assert report["workspace_filters"] is None


def test_explicit_workspace_selectors(tmp_path: Path, helper_script: Path) -> None:
    catalog = build_terminal_catalog(tmp_path)
    workspace = catalog.workspace_root
    other_workspace = catalog.other_workspace
    db_path = catalog.db_path

    output_path = workspace / "report_selected.json"
    cmd = [
        sys.executable,
        str(helper_script),
        "--db",
        str(db_path),
        "--output",
        str(output_path),
        "--workspace",
        ".",
        "--workspace",
        str(other_workspace),
    ]
    result = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    report = load_report(output_path)
    fingerprints = {entry["workspace_fingerprint"] for entry in report["entries"]}
    assert fingerprints == {
        compute_fingerprint(workspace),
        compute_fingerprint(other_workspace),
    }
    assert sorted(report["workspace_filters"]) == sorted(
        [compute_fingerprint(workspace), compute_fingerprint(other_workspace)]
    )
