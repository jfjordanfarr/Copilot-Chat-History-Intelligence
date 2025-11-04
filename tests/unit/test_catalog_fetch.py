from __future__ import annotations

import catalog
from catalog import ingest as catalog_ingest
from tests.helpers.catalog_builder import create_catalog_fixture, rich_session_payload


def _build_catalog(tmp_path, monkeypatch):
    fixture = create_catalog_fixture(tmp_path, sessions=[rich_session_payload()])
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


def test_fetch_tool_output_text_returns_fragments(tmp_path, monkeypatch):
    fixture = _build_catalog(tmp_path, monkeypatch)

    rows = catalog.fetch_tool_output_text(fixture.catalog_path)
    assert rows
    assert any(row["source_kind"] == "tool_output" for row in rows)
    assert any(row["source_kind"] == "tool_call_result" for row in rows)
    assert all(row["plain_text"] for row in rows)


def test_fetch_tool_output_text_supports_filters(tmp_path, monkeypatch):
    fixture = _build_catalog(tmp_path, monkeypatch)

    all_rows = catalog.fetch_tool_output_text(fixture.catalog_path)
    fingerprint = next(iter({row["workspace_fingerprint"] for row in all_rows}))

    filtered = catalog.fetch_tool_output_text(
        fixture.catalog_path,
        workspace_fingerprint=fingerprint,
        source_kinds=["tool_call_result"],
    )
    assert filtered
    assert {row["source_kind"] for row in filtered} == {"tool_call_result"}
    assert {row["workspace_fingerprint"] for row in filtered} == {fingerprint}

    limited = catalog.fetch_tool_output_text(fixture.catalog_path, limit=1)
    assert len(limited) == 1

    none_rows = catalog.fetch_tool_output_text(
        fixture.catalog_path,
        workspace_fingerprint="missing-fingerprint",
    )
    assert none_rows == []
