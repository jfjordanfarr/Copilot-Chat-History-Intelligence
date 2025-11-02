import json
import subprocess
import sys
from pathlib import Path

from tests.helpers.catalog_builder import create_catalog_fixture, minimal_session_payload


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_migrate_sandbox(tmp_path: Path) -> Path:
    fixture = create_catalog_fixture(
        tmp_path,
        sessions=[
            minimal_session_payload(
                prompt="Migration smoke query",
                response="Use migrate_sandbox.py to verify cloning",
            )
        ],
    )
    workspace = repo_root()
    sandbox_dir = tmp_path / "sandbox"
    summary_path = tmp_path / "migration-summary.json"
    script_path = workspace / "AI-Agent-Workspace" / "Workspace-Helper-Scripts" / "migrate_sandbox.py"

    command = [
        sys.executable,
        str(script_path),
        "--workspace-root",
        str(workspace),
        "--sandbox-dir",
        str(sandbox_dir),
        "--summary",
        str(summary_path),
        "--sessions",
        str(fixture.source_dir),
        "--recall-limit",
        "1",
    ]
    subprocess.run(command, check=True, cwd=workspace)
    return summary_path


def test_migration_sandbox_creates_catalog_and_exports(tmp_path):
    summary_path = run_migrate_sandbox(tmp_path)
    assert summary_path.exists(), "Migration summary was not written"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    sandbox_root = Path(summary["sandbox_root"])
    db_path = sandbox_root / ".vscode" / "CopilotChatHistory" / "copilot_chat_logs.db"
    export_dir = sandbox_root / "AI-Agent-Workspace" / "_temp" / "migration_exports"

    assert db_path.exists(), "Catalog database missing in sandbox"
    assert export_dir.exists(), "Export directory was not created"
    assert any(export_dir.rglob("*.md")), "No Markdown exports were generated"

    ingest_audit = summary.get("ingest", {}).get("audit", {})
    assert ingest_audit.get("requests_ingested", 0) > 0, "Ingestion did not report any requests"
    assert summary.get("sessions"), "Session list should not be empty"

    recall_info = summary.get("recall", {})
    assert recall_info.get("exit_code") == 0, "Recall CLI did not report success"
    assert recall_info.get("query"), "Recall query text was not captured"


def run_validate_census(tmp_path: Path, census_body: str, transcript_lines: int) -> subprocess.CompletedProcess:
    census_path = tmp_path / "census.md"
    census_path.write_text(census_body, encoding="utf-8")
    transcript_path = tmp_path / "transcript.md"
    transcript_path.write_text("\n".join(["line"] * transcript_lines) + "\n", encoding="utf-8")
    summary_path = tmp_path / "census-summary.json"

    script_path = repo_root() / "AI-Agent-Workspace" / "Workspace-Helper-Scripts" / "validate_census.py"
    command = [
        sys.executable,
        str(script_path),
        "--census",
        str(census_path),
        "--transcript",
        str(transcript_path),
        "--limit",
        "1200",
        "--summary",
        str(summary_path),
    ]
    return subprocess.run(command, cwd=repo_root(), capture_output=True, text=True)


def test_validate_census_passes_with_sequential_chunks(tmp_path):
    census_body = """
#### Lines 1-1200 — Segment A
#### Lines 1201-2400 — Segment B
""".strip()
    result = run_validate_census(tmp_path, census_body, transcript_lines=2400)
    assert result.returncode == 0, result.stdout + result.stderr


def test_validate_census_flags_excess_gap(tmp_path):
    census_body = """
#### Lines 1-1000 — Segment A
#### Lines 2301-2400 — Segment C
""".strip()
    result = run_validate_census(tmp_path, census_body, transcript_lines=2400)
    assert result.returncode != 0
    assert "Gap" in (result.stdout + result.stderr)
