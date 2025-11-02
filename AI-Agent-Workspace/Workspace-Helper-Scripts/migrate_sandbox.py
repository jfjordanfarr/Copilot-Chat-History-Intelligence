"""Run a migration dry run in a sandboxed workspace.

This helper copies the current repository to a throwaway directory, reruns the
catalog ingestion pipeline, regenerates Markdown exports, and exercises the
recall CLI. The resulting report documents the artefacts required by the
migration checklist.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

DEFAULT_SANDBOX = Path("AI-Agent-Workspace") / "_temp" / "migration_sandbox"
DEFAULT_SUMMARY = Path("AI-Agent-Workspace") / "_temp" / "migration_summary.json"
DEFAULT_REPEAT_FAILURES = Path("AI-Agent-Workspace") / "_temp" / "repeat_failures.json"
IGNORED_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
}
IGNORED_RELATIVE = {
    Path("AI-Agent-Workspace") / "_temp",
}


class MigrationError(RuntimeError):
    pass


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clone the workspace and verify migration tooling.")
    parser.add_argument("--workspace-root", type=Path, help="Workspace root to copy. Defaults to repository root.")
    parser.add_argument("--sandbox-dir", type=Path, help="Destination for the sandbox clone.")
    parser.add_argument("--sessions", type=Path, help="Optional directory or file with chat sessions to ingest.")
    parser.add_argument("--summary", type=Path, help="Optional path for the migration summary JSON.")
    parser.add_argument(
        "--repeat-failures-output",
        type=Path,
        help="Path for repeat-failure metrics JSON (default: AI-Agent-Workspace/_temp/repeat_failures.json).",
    )
    parser.add_argument(
        "--repeat-failures-baseline",
        type=Path,
        help="Optional baseline JSON used to compute repeat-failure deltas (defaults to the output path if it exists).",
    )
    parser.add_argument("--recall-limit", type=int, default=3, help="Maximum results to request from the recall CLI.")
    parser.add_argument("--keep", action="store_true", help="Keep existing sandbox directory instead of replacing it.")
    return parser.parse_args(argv)


def find_workspace_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").is_dir():
            return candidate
    raise MigrationError(f"Unable to locate repository root from {start}.")


def copy_workspace(source: Path, destination: Path, *, keep_existing: bool) -> None:
    if destination.exists() and not keep_existing:
        shutil.rmtree(destination)
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and keep_existing:
        return

    def ignore(path: str, names: Iterable[str]) -> List[str]:
        base = Path(path)
        ignored: List[str] = []
        for name in names:
            if name in IGNORED_NAMES:
                ignored.append(name)
                continue
            child = base / name
            for rel in IGNORED_RELATIVE:
                target = (source / rel).resolve()
                try:
                    child.resolve().relative_to(target)
                except ValueError:
                    continue
                ignored.append(name)
                break
        return ignored

    shutil.copytree(source, destination, dirs_exist_ok=False, ignore=ignore)


def build_env(pythonpath: Path) -> Dict[str, str]:
    env = os.environ.copy()
    current = env.get("PYTHONPATH", "")
    path_entries = [str(pythonpath)]
    if current:
        path_entries.append(current)
    env["PYTHONPATH"] = os.pathsep.join(path_entries)
    return env


def resolve_workspace_path(workspace_root: Path, candidate: Optional[Path], default: Path) -> Path:
    target = candidate or default
    if target.is_absolute():
        return target
    return (workspace_root / target).resolve()


def resolve_optional_path(workspace_root: Path, candidate: Optional[Path]) -> Optional[Path]:
    if candidate is None:
        return None
    if candidate.is_absolute():
        return candidate
    return (workspace_root / candidate).resolve()


def read_audit(sandbox_root: Path) -> Dict[str, object]:
    audit_path = sandbox_root / "AI-Agent-Workspace" / "_temp" / "ingest_audit.json"
    if not audit_path.exists():
        return {}
    try:
        return json.loads(audit_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def discover_sessions_source(workspace_root: Path) -> Optional[Path]:
    audit_path = workspace_root / "AI-Agent-Workspace" / "_temp" / "ingest_audit.json"
    if audit_path.exists():
        try:
            payload = json.loads(audit_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            files = payload.get("files")
            if isinstance(files, list):
                parents = []
                for item in files:
                    if not isinstance(item, str):
                        continue
                    parent = Path(item).parent
                    if parent not in parents and parent.exists():
                        parents.append(parent)
                if parents:
                    return parents[0]
    raw_json_dir = workspace_root / "AI-Agent-Workspace" / "Project-Chat-History" / "Raw-JSON"
    if raw_json_dir.exists() and any(raw_json_dir.glob("*.json")):
        return raw_json_dir
    return None


def collect_sessions(db_path: Path) -> List[str]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT session_id FROM chat_sessions ORDER BY last_message_date_ms DESC"
        ).fetchall()
    return [str(row["session_id"]) for row in rows if row["session_id"]]


def choose_recall_query(db_path: Path) -> Optional[str]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT command_text FROM metrics_repeat_failures WHERE command_text != '' ORDER BY occurrence_count DESC, last_seen_ms DESC LIMIT 1"
        ).fetchone()
        if row and row["command_text"]:
            candidate = str(row["command_text"]).strip()
            if candidate:
                return candidate
        row = conn.execute(
            "SELECT prompt_text FROM requests WHERE prompt_text != '' ORDER BY timestamp_ms DESC LIMIT 1"
        ).fetchone()
        if row and row["prompt_text"]:
            candidate = str(row["prompt_text"]).strip()
            if candidate:
                return candidate
    return None


def run_command(command: Sequence[str], *, cwd: Path, env: Dict[str, str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, cwd=cwd, env=env, check=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    script_path = Path(__file__).resolve()
    workspace_root = (args.workspace_root or find_workspace_root(script_path.parent)).resolve()
    sandbox_root = (args.sandbox_dir or DEFAULT_SANDBOX).resolve()
    summary_path = (args.summary or DEFAULT_SUMMARY).resolve()
    repeat_failures_output = resolve_workspace_path(workspace_root, args.repeat_failures_output, DEFAULT_REPEAT_FAILURES)
    repeat_failures_baseline = resolve_optional_path(workspace_root, args.repeat_failures_baseline)
    if repeat_failures_baseline is None and repeat_failures_output.exists():
        repeat_failures_baseline = repeat_failures_output
    sessions_path = args.sessions.resolve() if args.sessions else None
    if sessions_path and not sessions_path.exists():
        raise MigrationError(f"Chat session path not found: {sessions_path}")
    if sessions_path is None:
        sessions_path = discover_sessions_source(workspace_root)
        if sessions_path:
            print(f"Discovered chat sessions at {sessions_path}")

    print(f"Preparing sandbox at {sandbox_root}")
    copy_workspace(workspace_root, sandbox_root, keep_existing=args.keep)

    catalog_dir = sandbox_root / ".vscode" / "CopilotChatHistory"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    db_path = catalog_dir / "copilot_chat_logs.db"
    env = build_env(sandbox_root / "src")

    print("Running catalog.ingest ...")
    ingest_cmd: List[str] = [
        sys.executable,
        "-m",
        "catalog.ingest",
        "--db",
        str(db_path),
        "--output-dir",
        str(catalog_dir),
        "--workspace-root",
        str(sandbox_root),
        "--reset",
    ]
    if sessions_path:
        ingest_cmd.append(str(sessions_path))

    run_command(ingest_cmd, cwd=sandbox_root, env=env)
    audit = read_audit(sandbox_root)

    export_dir = sandbox_root / "AI-Agent-Workspace" / "_temp" / "migration_exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    print("Rendering exports ...")
    export_cmd: List[str] = [
        sys.executable,
        "-m",
        "export.cli",
        "--database",
        str(db_path),
        "--all",
        "--include-status",
        "--workspace-directories",
        "--output",
        str(export_dir),
    ]
    run_command(export_cmd, cwd=sandbox_root, env=env)

    recall_query = choose_recall_query(db_path)
    recall_cmd: Optional[List[str]] = None
    recall_exit: Optional[int] = None
    if recall_query:
        print(f"Running recall for '{recall_query}' ...")
        recall_cmd = [
            sys.executable,
            "-m",
            "recall.conversation_recall",
            recall_query,
            "--db",
            str(db_path),
            "--limit",
            str(max(1, args.recall_limit)),
            "--print-latency",
        ]
        result = run_command(recall_cmd, cwd=sandbox_root, env=env)
        recall_exit = result.returncode
    else:
        print("Skipping recall step (no suitable query found).")

    repeat_failures_cmd: Optional[List[str]] = None
    repeat_failures_exit: Optional[int] = None
    repeat_failures_entries: Optional[int] = None
    measure_script = sandbox_root / "AI-Agent-Workspace" / "Workspace-Helper-Scripts" / "measure_repeat_failures.py"
    if measure_script.exists():
        repeat_failures_cmd = [
            sys.executable,
            str(measure_script),
            "--db",
            str(db_path),
            "--output",
            str(repeat_failures_output),
        ]
        if repeat_failures_baseline:
            repeat_failures_cmd.extend(["--baseline", str(repeat_failures_baseline)])
        print(f"Recording repeat-failure metrics to {repeat_failures_output} ...")
        result = run_command(repeat_failures_cmd, cwd=sandbox_root, env=env)
        repeat_failures_exit = result.returncode
        try:
            payload = json.loads(repeat_failures_output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            repeat_failures_entries = None
        else:
            if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
                repeat_failures_entries = len(payload["entries"])
            elif isinstance(payload, list):
                repeat_failures_entries = len(payload)
    else:
        print("Skipping repeat-failure metrics (helper script not found).")

    exported_files = sorted(str(path.relative_to(export_dir)) for path in export_dir.rglob("*.md"))
    sessions = collect_sessions(db_path)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(workspace_root),
        "sandbox_root": str(sandbox_root),
        "catalog_db": str(db_path),
        "ingest": {
            "command": ingest_cmd,
            "audit": audit,
        },
        "exports": {
            "command": export_cmd,
            "output_dir": str(export_dir),
            "files": exported_files,
        },
        "recall": {
            "command": recall_cmd,
            "query": recall_query,
            "exit_code": recall_exit,
        },
        "repeat_failures": {
            "command": repeat_failures_cmd,
            "output": str(repeat_failures_output),
            "baseline": str(repeat_failures_baseline) if repeat_failures_baseline else None,
            "exit_code": repeat_failures_exit,
            "entries": repeat_failures_entries,
        },
        "sessions": sessions,
        "chat_source": str(sessions_path) if sessions_path else None,
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Migration summary written to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
