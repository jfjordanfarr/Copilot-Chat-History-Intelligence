import sqlite3
import json
import sys
from pathlib import Path

DB_PATH = Path('AI-Agent-Workspace/live_chat.db')

if not DB_PATH.exists():
    raise SystemExit(f'Database not found at {DB_PATH}')

query = 'autosummarization' if len(sys.argv) < 2 else sys.argv[1].lower()

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
try:
    matches = []
    for row in conn.execute('SELECT prompt_id, raw_json FROM prompts'):
        entry = json.loads(row['raw_json'])
        for log in entry.get('logs', []):
            if log.get('kind') != 'response':
                continue
            metadata = log.get('result', {}).get('metadata')
            if not isinstance(metadata, dict):
                continue
            summary = metadata.get('summary')
            if isinstance(summary, str) and query in summary.lower():
                snippet = summary.replace('\n', ' ')
                matches.append((row['prompt_id'], snippet))
    if matches:
        for prompt_id, snippet in matches[:10]:
            print(f'{prompt_id} -> {snippet[:140]}')
        if len(matches) > 10:
            print(f'... {len(matches) - 10} more')
    else:
        print('No matches found')
finally:
    conn.close()
