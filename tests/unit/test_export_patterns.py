"""Unit tests for src.export.patterns terminal formatting."""

from __future__ import annotations

from src.export.patterns import render_message_stream


def _terminal_messages(*, exit_code: int, stderr: str | None = None, invocation: str | None = None) -> list[dict]:
    return [
        {
            "kind": "prepareToolInvocation",
            "toolName": "run_in_terminal",
            "toolSpecificData": {
                "commandLine": {"original": "pytest -k critical"},
            },
        },
        {
            "kind": "toolInvocationSerialized",
            "toolName": "run_in_terminal",
            "invocationMessage": invocation,
            "toolSpecificData": {
                "commandLine": {"original": "pytest -k critical"},
                "toolResult": {
                    "exitCode": exit_code,
                    "stderr": stderr,
                    "durationMs": 1250,
                    "cwd": "d:/repo/project",
                },
                "cwd": "d:/repo/project",
                "language": "powershell",
            },
        },
    ]


def test_terminal_failure_includes_tail_and_status() -> None:
    messages = _terminal_messages(exit_code=1, stderr="Traceback\nError: boom", invocation="Running pytest")
    messages.append({"kind": "progressTaskSerialized", "title": "Awaiting input"})
    blocks = render_message_stream(messages, include_raw=False)
    assert blocks, "Expected at least one rendered block"
    lines = blocks[0]
    assert lines[0].startswith("**Terminal**")
    assert "→ exit 1" in lines[0]
    assert any(line.startswith("Running pytest") for line in lines)
    assert any("Last stderr lines" in line for line in lines)
    assert any("Awaiting input" in line for line in lines)
    assert any(line.startswith("Duration:") for line in lines)
    assert any(line.startswith("CWD:") for line in lines)
    assert any(line.startswith("Shell:") for line in lines)


def test_terminal_warning_annotates_tail() -> None:
    messages = _terminal_messages(exit_code=0, stderr="warning: minor issue")
    blocks = render_message_stream(messages, include_raw=False)
    lines = blocks[0]
    assert lines[0].endswith("→ ✓"), lines[0]
    warning_lines = [line for line in lines if "Warnings" in line]
    assert warning_lines, "Expected warning tail to be surfaced"
