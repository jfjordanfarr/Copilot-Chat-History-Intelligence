import subprocess
import sys
from pathlib import Path
from typing import List

import pytest


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def helper_scripts_dir() -> Path:
    return repo_root() / "AI-Agent-Workspace" / "Workspace-Helper-Scripts"


CLI_CASES = [
    (
        "catalog_ingest_module",
        [sys.executable, "-m", "catalog.ingest", "--help"],
        ["--reset", "--db"],
    ),
    (
        "export_cli_module",
        [sys.executable, "-m", "export.cli", "--help"],
        ["--database", "--include-status"],
    ),
    (
        "recall_conversation_module",
        [sys.executable, "-m", "recall.conversation_recall", "--help"],
        ["--print-latency", "--workspace"],
    ),
    (
        "migrate_sandbox_script_win",
        [sys.executable, str(helper_scripts_dir() / "migrate_sandbox.py"), "--help"],
        ["--repeat-failures-output", "--repeat-failures-baseline"],
    ),
    (
        "migrate_sandbox_script_posix",
        [sys.executable, (helper_scripts_dir() / "migrate_sandbox.py").as_posix(), "--help"],
        ["--repeat-failures-output", "--keep"],
    ),
    (
        "validate_census_script",
        [sys.executable, str(helper_scripts_dir() / "validate_census.py"), "--help"],
        ["--summary", "--limit"],
    ),
    (
        "measure_repeat_failures_script",
        [sys.executable, str(helper_scripts_dir() / "measure_repeat_failures.py"), "--help"],
        ["--baseline", "--security-report", "--workspace", "--all-workspaces"],
    ),
]


@pytest.mark.parametrize("label, command, expected_flags", CLI_CASES)
def test_cli_help_runs(label: str, command: List[str], expected_flags: List[str]) -> None:
    result = subprocess.run(
        command,
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{label} help command failed: {result.stderr}"
    stdout_lower = result.stdout.lower()
    for flag in expected_flags:
        assert flag in stdout_lower, f"{label} help output missing flag {flag}"