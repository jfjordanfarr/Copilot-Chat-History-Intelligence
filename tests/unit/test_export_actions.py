"""Unit tests for src.export.actions helpers."""

from __future__ import annotations

from src.export.actions import RenderedActions, render_actions


def _terminal_message(command: str, *, exit_code: int = 0, stderr: str | None = None) -> list[dict]:
    return [
        {
            "kind": "prepareToolInvocation",
            "toolName": "run_in_terminal",
            "toolSpecificData": {
                "commandLine": {"original": command},
            },
        },
        {
            "kind": "toolInvocationSerialized",
            "toolName": "run_in_terminal",
            "toolSpecificData": {
                "commandLine": {"original": command},
                "toolResult": {
                    "exitCode": exit_code,
                    "stderr": stderr,
                },
            },
        },
    ]


def _search_message(pattern: str, *, include_pattern: str | None = None) -> list[dict]:
    return [
        {
            "kind": "prepareToolInvocation",
            "toolName": "grep_search",
            "toolSpecificData": {
                "query": pattern,
            },
        },
        {
            "kind": "toolInvocationSerialized",
            "toolName": "grep_search",
            "toolSpecificData": {
                "query": pattern,
                "includePattern": include_pattern,
            },
        },
    ]


def test_render_actions_counts_and_noise_suppression() -> None:
    messages = []
    messages.extend(_terminal_message("pytest -k flaky_test", exit_code=1, stderr="Error: boom"))
    messages.append({"kind": "thinking", "message": "checking"})
    rendered = render_actions(messages)
    assert isinstance(rendered, RenderedActions)
    assert rendered.counts == {"Terminal": 1}
    assert any(line.startswith("**Terminal**") for line in rendered.lines)
    assert all("thinking" not in line.lower() for line in rendered.lines)


def test_render_actions_multiple_action_types() -> None:
    messages = []
    messages.extend(_terminal_message("npm test"))
    messages.extend(_search_message("TODO", include_pattern="src/**"))
    rendered = render_actions(messages)
    assert rendered.counts == {"Search": 1, "Terminal": 1}
    assert "**Terminal**" in rendered.lines[0]
    assert any(line.startswith("**Search**") for line in rendered.lines)


def test_render_actions_include_raw_payload() -> None:
    messages = []
    messages.extend(_terminal_message("python script.py"))
    rendered = render_actions(messages, include_raw=True)
    assert rendered.counts["Terminal"] == 1
    # Raw payloads should be present when include_raw=True
    assert any(line == "```json" for line in rendered.lines)
