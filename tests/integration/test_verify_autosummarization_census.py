from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

HELPER = Path("AI-Agent-Workspace/Workspace-Helper-Scripts/verify_autosummarization_census.py")


def _write_catalog(
    db_path: Path,
    prompts: Sequence[str],
    *,
    fingerprint: str | None = None,
    fingerprints: Sequence[str] | None = None,
    session_prefix: str = "session",
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                request_id TEXT PRIMARY KEY,
                session_id TEXT,
                workspace_fingerprint TEXT,
                prompt_text TEXT
            )
            """
        )
        for index, prompt in enumerate(prompts):
            current_fingerprint = (
                fingerprints[index]
                if fingerprints is not None
                else fingerprint or "fingerprint_a"
            )
            conn.execute(
                "INSERT INTO requests (request_id, session_id, workspace_fingerprint, prompt_text) VALUES (?, ?, ?, ?)",
                (
                    f"request_{index}",
                    f"{session_prefix}_{index}",
                    current_fingerprint,
                    prompt,
                ),
            )
        conn.commit()


def _write_census(census_path: Path, chunks: list[str]) -> None:
    census_path.parent.mkdir(parents=True, exist_ok=True)
    census_path.write_text("\n".join(chunks), encoding="utf-8")


def _run_helper(
    db_path: Path,
    census_path: Path,
    *,
    limit: int = 1200,
    extra_args: Iterable[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(HELPER),
        "--db",
        str(db_path),
        "--census",
        str(census_path),
        "--limit",
        str(limit),
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def test_verify_autosummarization_census_passes_when_chunks_cover_ranges(tmp_path):
    db_path = tmp_path / "catalog.db"
    census_path = tmp_path / ".mdmd" / "user-intent-census.md"
    _write_catalog(
        db_path,
        [
            "You came out of a lossy autosummarization step. #file:2025-11-02.md:100-200",
            "No autosummarization here",
        ],
    )
    _write_census(
        census_path,
        [
            "# User Intent Census",
            "#### [2025-11-02] Lines 1 - 220 — Recovery block",
        ],
    )

    result = _run_helper(db_path, census_path)

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Prompts without coverage: 0" in result.stdout


def test_verify_autosummarization_census_flags_missing_coverage(tmp_path):
    db_path = tmp_path / "catalog.db"
    census_path = tmp_path / ".mdmd" / "user-intent-census.md"
    _write_catalog(
        db_path,
        [
            "Rehydrate after autosummarization. #file:2025-10-31.md:400-520",
        ],
    )
    _write_census(
        census_path,
        [
            "# User Intent Census",
            "#### [2025-10-31] Lines 100 - 399 — Earlier block",
        ],
    )

    result = _run_helper(db_path, census_path)

    assert result.returncode == 1
    assert "Missing coverage" in result.stdout


def test_workspace_filter_limits_prompts(tmp_path):
    db_path = tmp_path / "catalog.db"
    census_path = tmp_path / ".mdmd" / "user-intent-census.md"
    _write_catalog(
        db_path,
        [
            "Hydrate after autosummarization. #file:2025-11-02.md:10-12",
            "Different workspace autosummarization. #file:2025-11-02.md:10-12",
        ],
        fingerprints=["fingerprint_a", "fingerprint_b"],
    )
    _write_census(
        census_path,
        [
            "# User Intent Census",
            "#### [2025-11-02] Lines 1 - 50 — Coverage chunk",
        ],
    )

    result = _run_helper(
        db_path,
        census_path,
        extra_args=["--workspace-fingerprint", "fingerprint_a"],
    )

    assert "Total prompts scanned: 1" in result.stdout
    assert result.returncode == 0


def test_ignore_label_skips_references(tmp_path):
    db_path = tmp_path / "catalog.db"
    census_path = tmp_path / ".mdmd" / "user-intent-census.md"
    _write_catalog(
        db_path,
        [
            "Ignore autosummarization. #file:other.md:10-20",
        ],
    )
    _write_census(
        census_path,
        [
            "# User Intent Census",
            "#### [other] Lines 1 - 30 — Placeholder coverage",
        ],
    )

    result = _run_helper(
        db_path,
        census_path,
        extra_args=["--ignore-label", "other"],
    )

    assert "References ignored via label filter: 1" in result.stdout
    assert result.returncode == 0


def test_multi_chunk_coverage_succeeds(tmp_path):
    db_path = tmp_path / "catalog.db"
    census_path = tmp_path / ".mdmd" / "user-intent-census.md"
    _write_catalog(
        db_path,
        [
            "Check two chunks. #file:2025-11-02.md:10-220",
        ],
    )
    _write_census(
        census_path,
        [
            "# User Intent Census",
            "#### [2025-11-02] Lines 1 - 120 — First chunk",
            "#### [2025-11-02] Lines 121 - 240 — Second chunk",
        ],
    )

    result = _run_helper(db_path, census_path)

    assert result.returncode == 0
    assert "Missing coverage: 0" in result.stdout


def test_foreign_workspace_prompts_are_skipped_by_default(tmp_path):
    db_path = tmp_path / "catalog.db"
    census_path = tmp_path / ".mdmd" / "user-intent-census.md"
    _write_catalog(
        db_path,
        [
            "Rehydrate (insiders) after autosummarization. #file:2025-11-03.md:10-40",
            "Rehydrate follow-up autosummarization. #file:2025-11-03.md:50-80",
            "Foreign workspace autosummarization span. #file:2025-11-03.md:400-420",
        ],
        fingerprints=["fingerprint_insiders", "fingerprint_insiders", "fingerprint_other"],
    )
    _write_census(
        census_path,
        [
            "# User Intent Census",
            "#### [2025-11-03] Lines 1 - 120 — Insiders coverage",
        ],
    )

    result = _run_helper(db_path, census_path)

    assert result.returncode == 0
    assert "Prompts skipped via workspace filter: 1" in result.stdout
    assert "Missing coverage: 0" in result.stdout
    assert "Missing coverage for" not in result.stdout


def test_foreign_references_detected_via_embedded_fingerprint(tmp_path):
    db_path = tmp_path / "catalog.db"
    census_path = tmp_path / ".mdmd" / "user-intent-census.md"
    local_fp = "5a70ddd9b8cd03e5"
    foreign_fp = "bcafd8920edd0917"
    _write_catalog(
        db_path,
        [
            (
                "score=0.71 request=<local> autosummarization fingerprint="
                + local_fp
                + "\n  Prompt: #file:2025-11-02.md:10-20"
            ),
            (
                "score=0.42 request=<foreign> autosummarization fingerprint="
                + foreign_fp
                + "\n  Prompt: #file:2025-10-28.md:1-40"
            ),
        ],
        fingerprints=[local_fp, local_fp],
    )
    _write_census(
        census_path,
        [
            "# User Intent Census",
            "#### [2025-11-02] Lines 1 - 80 — Local coverage",
        ],
    )

    result = _run_helper(
        db_path,
        census_path,
        extra_args=["--workspace-fingerprint", local_fp],
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "References skipped via workspace filter: 1" in result.stdout
    assert "Missing coverage: 0" in result.stdout
