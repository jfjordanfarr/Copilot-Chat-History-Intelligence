"""Integration tests for the markdown exporter."""

from __future__ import annotations

from pathlib import Path

from src.export.markdown import render_session_markdown


def _build_session_fixture() -> dict:
    session = {
        "sessionId": "session-001",
        "requesterUsername": "dev@example",
        "responderUsername": "GitHub Copilot",
        "initialLocation": "panel",
        "workspaceKey": "workspace-main",
        "creationDate": 1700000000000,
        "lastMessageDate": 1700000060000,
        "requests": [],
    }

    turn1 = {
        "requestId": "turn-1",
        "message": {"text": "Help me debug the failing tests."},
        "timestamp": 1700000000000,
        "contentReferences": [
            {
                "label": "tests/test_example.py",
                "reference": {
                    "uri": {"scheme": "file", "path": "/workspace/tests/test_example.py"},
                    "range": {"startLineNumber": 12, "endLineNumber": 18},
                },
            }
        ],
        "response": [
            {
                "value": "I can help run the suite and inspect failures.",
                "supportThemeIcons": False,
                "supportHtml": False,
            }
        ],
        "result": {
            "metadata": {
                "thinking": {"text": "Checking previous runs..."},
                "messages": [
                    {
                        "kind": "prepareToolInvocation",
                        "toolName": "run_in_terminal",
                        "toolSpecificData": {
                            "commandLine": {"original": "pytest -k flaky_test"},
                        },
                    },
                    {
                        "kind": "toolInvocationSerialized",
                        "toolName": "run_in_terminal",
                        "invocationMessage": "Running terminal command",
                        "toolSpecificData": {
                            "commandLine": {"original": "pytest -k flaky_test"},
                            "toolResult": {
                                "exitCode": 1,
                                "stderr": "E   AssertionError: boom\nFAILED tests/test_example.py::test_example",
                                "durationMs": 1540,
                                "cwd": "d:/repo/project",
                            },
                            "cwd": "d:/repo/project",
                            "language": "powershell",
                        },
                    },
                    {
                        "kind": "progressTaskSerialized",
                        "title": "Awaiting input from user",
                    },
                ],
                "toolInvocations": [
                    {
                        "name": "run_in_terminal",
                        "args": {"command": "pytest -k flaky_test"},
                        "result": {
                            "exitCode": 1,
                            "stderr": "E   AssertionError: boom\nFAILED tests/test_example.py::test_example",
                            "durationMs": 1540,
                        },
                    }
                ],
            },
            "errorDetails": {"message": "Terminal exited with code 1"},
        },
        "followups": ["Try running with -vv"],
        "isCanceled": False,
    }

    turn2 = {
        "requestId": "turn-2",
        "message": {"text": "Apply the suggested fix."},
        "timestamp": 1700000030000,
        "response": [
            {"value": "Applied the patch and re-ran tests.", "supportThemeIcons": False, "supportHtml": False}
        ],
        "result": {
            "metadata": {
                "messages": [
                    {
                        "kind": "prepareToolInvocation",
                        "toolName": "copilot_applyPatch",
                        "toolSpecificData": {"toolId": "copilot_applyPatch"},
                    },
                    {
                        "kind": "toolInvocationSerialized",
                        "toolName": "copilot_applyPatch",
                        "toolSpecificData": {
                            "toolId": "copilot_applyPatch",
                            "toolResult": {"exitCode": 0},
                        },
                    },
                    {
                        "kind": "textEditGroup",
                        "edits": [
                            {
                                "uri": {"scheme": "file", "path": "/workspace/src/example.py"},
                                "range": {"startLineNumber": 10, "endLineNumber": 15},
                                "text": "print(\"fixed\")\n",
                            }
                        ],
                    },
                    {
                        "kind": "undoStop",
                    },
                    {
                        "kind": "prepareToolInvocation",
                        "toolName": "run_in_terminal",
                        "toolSpecificData": {
                            "commandLine": {"original": "pytest"},
                        },
                    },
                    {
                        "kind": "toolInvocationSerialized",
                        "toolName": "run_in_terminal",
                        "toolSpecificData": {
                            "commandLine": {"original": "pytest"},
                            "toolResult": {
                                "exitCode": 0,
                                "stderr": "DeprecationWarning: pending",
                                "durationMs": 980,
                            },
                            "cwd": "d:/repo/project",
                        },
                    },
                    {
                        "kind": "prepareToolInvocation",
                        "toolName": "run_in_terminal",
                        "toolSpecificData": {
                            "commandLine": {"original": "pytest"},
                        },
                    },
                    {
                        "kind": "toolInvocationSerialized",
                        "toolName": "run_in_terminal",
                        "toolSpecificData": {
                            "commandLine": {"original": "pytest"},
                            "toolResult": {
                                "exitCode": 0,
                                "durationMs": 900,
                            },
                            "cwd": "d:/repo/project",
                        },
                    },
                    {
                        "kind": "prepareToolInvocation",
                        "toolName": "run_in_terminal",
                        "toolSpecificData": {
                            "commandLine": {"original": "pytest"},
                        },
                    },
                    {
                        "kind": "toolInvocationSerialized",
                        "toolName": "run_in_terminal",
                        "toolSpecificData": {
                            "commandLine": {"original": "pytest"},
                            "toolResult": {
                                "exitCode": 0,
                                "durationMs": 905,
                            },
                            "cwd": "d:/repo/project",
                        },
                    },
                ]
            }
        },
        "followups": [],
        "isCanceled": False,
    }

    turn3 = {
        "requestId": "turn-3",
        "message": {"text": "Stop running commands."},
        "timestamp": 1700000050000,
        "response": None,
        "result": {
            "metadata": {"messages": []},
            "errorDetails": {"message": "User canceled the request"},
        },
        "isCanceled": True,
        "followups": [],
    }

    session["requests"].extend([turn1, turn2, turn3])
    return session


def test_render_session_markdown_golden(tmp_path: Path) -> None:
    session = _build_session_fixture()
    cross_dir = tmp_path / "exports"
    cross_dir.mkdir()
    (cross_dir / "previous.md").write_text(
        """# Copilot Chat Session — previous\n\n## Turn 1\n\n#### Actions\n**Terminal** — pytest → ✓\nDuration: 900 ms\nCWD: d:\\repo\\project\n""",
        encoding="utf-8",
    )
    output = render_session_markdown(session, include_status=True, cross_session_dir=cross_dir)
    golden_path = Path(__file__).parent / "golden" / "session_basic.md"
    expected = golden_path.read_text(encoding="utf-8")
    assert output == expected


def test_render_session_markdown_lod0() -> None:
    session = _build_session_fixture()
    output = render_session_markdown(session, include_status=False, lod_level=0)
    assert "GitHub Copilot:" in output
    assert "### USER" not in output
    assert "#### Actions" not in output
