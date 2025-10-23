import sqlite3
import json
import pprint
import sys
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parent / "vscode-copilot-chat-main"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

from script.copilot_markdown.utils import prune_keys


MAX_SNIPPET = 800
SENSITIVE_KEYS = {"encrypted"}


def print_first(label: str, payload):
    """Print the first entry from a list/dict payload for quick inspection."""
    if isinstance(payload, list):
        if payload:
            print(f"--- first {label} (list) ---")
            print(_summarize(payload[0]))
        else:
            print(f"--- {label} list is empty ---")
    elif isinstance(payload, dict):
        try:
            first_key = next(iter(payload))
        except StopIteration:
            print(f"--- {label} dict is empty ---")
            return
        print(f"--- first {label} entry: {first_key!r} ---")
        print(_summarize(payload[first_key]))
    else:
        print(f"--- {label} is unexpected type: {type(payload).__name__} ---")
        print(_summarize(payload))


def _summarize(value) -> str:
    """Return a printable summary string clipped to MAX_SNIPPET."""
    cleaned = prune_keys(value, SENSITIVE_KEYS)
    formatted = pprint.pformat(cleaned, depth=4, width=80, compact=True)
    if len(formatted) <= MAX_SNIPPET:
        return formatted
    return formatted[:MAX_SNIPPET] + "... <truncated>"

conn = sqlite3.connect(r'c:/Users/User/Downloads/vscode-copilot-chat-main/AI-Agent-Workspace/live_chat.db')
conn.row_factory = sqlite3.Row
row = conn.execute('SELECT raw_json FROM prompts WHERE prompt_id=?', ('9708e843-98b5-438c-89da-f2758c798075',)).fetchone()
conn.close()
if not row:
    raise SystemExit('prompt not found')
entry = json.loads(row['raw_json'])
for log in entry.get('logs', []):
    if log.get('kind') != 'response':
        continue
    result = log.get('result')
    if not isinstance(result, dict):
        continue
    metadata = result.get('metadata')
    if not isinstance(metadata, dict):
        continue
    messages = metadata.get('messages')
    invocations = metadata.get('toolInvocations')
    rounds = metadata.get('toolCallRounds')
    results = metadata.get('toolCallResults')
    print('found response with metadata; messages?', bool(messages), 'invocations?', bool(invocations), 'rounds?', bool(rounds), 'results?', bool(results))
    if messages:
        print_first('response message', messages)
    results_map = {}
    if isinstance(results, dict):
        results_map = results
    elif isinstance(results, list):
        for payload in results:
            if not isinstance(payload, dict):
                continue
            call_id = payload.get('callId') or payload.get('toolCallId') or payload.get('id')
            if call_id:
                results_map[str(call_id)] = payload

    if rounds:
        print_first('toolCallRound', rounds)
        print(f"total rounds: {len(rounds)}")
        first_round = rounds[0]
        tool_calls = first_round.get('toolCalls') if isinstance(first_round, dict) else None
        if isinstance(tool_calls, list):
            print(f"round0 tool_calls: {len(tool_calls)} entries")
            for call in tool_calls[:3]:
                if not isinstance(call, dict):
                    continue
                call_id = call.get('id') or call.get('toolCallId')
                name = call.get('name') or call.get('toolName') or call.get('toolId')
                args = call.get('arguments') or call.get('input') or call.get('args')
                print(f"  call id={call_id!r} name={name!r}")
                if isinstance(args, str):
                    preview = args
                else:
                    preview = json.dumps(args, ensure_ascii=False) if args is not None else None
                if preview:
                    if len(preview) > 160:
                        preview = preview[:160] + '…'
                    print(f"    args preview: {preview}")
                call_messages = prune_keys(call.get('messages'), SENSITIVE_KEYS)
                if isinstance(call_messages, list) and call_messages:
                    print('    messages snapshot:', [m.get('kind') for m in call_messages[:3] if isinstance(m, dict)])
                    print('    first message detail:', json.dumps(call_messages[0], ensure_ascii=False)[:200])
                if call_id and call_id in results_map:
                    payload = results_map[call_id]
                    print(f"    result for {call_id}: keys={sorted(payload.keys())}")
                    status = payload.get('status')
                    if status:
                        print(f"    status={status!r}")
                    if 'content' in payload:
                        content = payload['content']
                        if isinstance(content, list) and content:
                            preview = json.dumps(content[0], ensure_ascii=False)
                            if len(preview) > 200:
                                preview = preview[:200] + '…'
                            print(f"    content[0] preview: {preview}")

            # Print any run_in_terminal calls beyond the first three for debugging statuses.
            for call in tool_calls[3:]:
                if not isinstance(call, dict):
                    continue
                name = call.get('name') or call.get('toolName') or call.get('toolId')
                if name != 'run_in_terminal':
                    continue
                call_id = call.get('id') or call.get('toolCallId')
                print(f"  (extra) run_in_terminal id={call_id!r}")
                args = call.get('arguments') or call.get('input') or call.get('args')
                if isinstance(args, str):
                    arg_preview = args
                else:
                    arg_preview = json.dumps(args, ensure_ascii=False) if args is not None else None
                if arg_preview:
                    if len(arg_preview) > 160:
                        arg_preview = arg_preview[:160] + '…'
                    print(f"    args preview: {arg_preview}")
                if call_id and call_id in results_map:
                    payload = prune_keys(results_map[call_id], SENSITIVE_KEYS)
                    print(f"    result keys={sorted(payload.keys())}")
                    status = payload.get('status')
                    if status:
                        print(f"    status={status!r}")
                    content = payload.get('content')
                    if isinstance(content, list) and content:
                        preview = json.dumps(content[0], ensure_ascii=False)
                        if len(preview) > 200:
                            preview = preview[:200] + '…'
                        print(f"    content[0] preview: {preview}")
    if results:
        print_first('toolCallResult', results)
        if isinstance(results, dict):
            first_key = next(iter(results), None)
            if first_key:
                payload = results[first_key]
                if isinstance(payload, dict):
                    print('    toolCallResult keys:', sorted(payload.keys()))
                    for key in ('status', 'invocationMessage', 'resultMessage', 'isError'):
                        if key in payload:
                            print(f"    {key}: {payload[key]!r}")
                    content = payload.get('content')
                    if isinstance(content, list) and content:
                        first_part = content[0]
                        print('    content[0] type:', type(first_part).__name__)
                        if isinstance(first_part, dict):
                            print('    content[0] keys:', sorted(first_part.keys()))
                            node = first_part.get('value')
                            if isinstance(node, dict):
                                keys = sorted(node.keys())
                                print(f"    value keys: {keys}")
                                node_preview = json.dumps(node, ensure_ascii=False)
                                if len(node_preview) > 200:
                                    node_preview = node_preview[:200] + '…'
                                print(f"    value preview: {node_preview}")
    if invocations:
        print_first('tool invocation', invocations)
    print('--- metadata keys ---', list(metadata.keys()))
    print()
