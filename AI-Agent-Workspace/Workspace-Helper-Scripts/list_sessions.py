import json
import sqlite3
from pathlib import Path

def main() -> None:
    db_path = Path(__file__).with_name("live_chat.db")
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT prompt_id, raw_json FROM prompts").fetchall()
    records = []
    for row in rows:
        try:
            payload = json.loads(row["raw_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        session = payload.get("session")
        if not isinstance(session, dict):
            continue
        session_id = session.get("sessionId") or row["prompt_id"]
        created = session.get("creationDate") or 0
        last = session.get("lastMessageDate") or created or 0
        records.append((last, session_id, created))
    records.sort(reverse=True)
    for last, session_id, created in records[:20]:
        print(f"{session_id}\t{last}\t{created}")

if __name__ == "__main__":
    main()
