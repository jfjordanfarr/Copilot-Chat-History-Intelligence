from __future__ import annotations

from catalog.rich_text import extract_text_fragments, flatten_structured_text


def test_extract_text_fragments_normalises_newlines() -> None:
    fragments = extract_text_fragments("Line 1\r\nLine 2\rLine 3")
    assert fragments == ["Line 1\nLine 2\nLine 3"]


def test_flatten_structured_text_handles_nested_payload() -> None:
    payload = {
        "value": [
            {"text": "First"},
            {"value": '{"node":{"children":[{"text":"Second"}]}}'},
            {"messages": [{"text": "Third"}]},
        ]
    }

    combined = flatten_structured_text(payload)
    assert combined == "First\nSecond\nThird"


def test_flatten_structured_text_returns_empty_string_for_missing_text() -> None:
    payload = {"value": {"metadata": {"type": "noop"}}}
    assert flatten_structured_text(payload) == ""
