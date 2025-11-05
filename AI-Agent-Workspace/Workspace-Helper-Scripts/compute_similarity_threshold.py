from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from analysis import similarity_threshold as similarity_threshold_module

DEFAULT_DB_PATH = Path(".vscode") / "CopilotChatHistory" / "copilot_chat_logs.db"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute the actionable similarity threshold from metrics_repeat_failures telemetry.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to the normalized Copilot catalog database (defaults to .vscode/CopilotChatHistory/copilot_chat_logs.db).",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=similarity_threshold_module.DEFAULT_WINDOW_DAYS,
        help="Number of days to consider when sampling telemetry (default: %(default)s).",
    )
    parser.add_argument(
        "--percentile",
        type=float,
        default=similarity_threshold_module.DEFAULT_PERCENTILE,
        help="Percentile used to derive the threshold (default: %(default)s).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON file to persist the computed threshold and metadata.",
    )
    return parser.parse_args(argv)


def write_output(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    db_path = args.db.expanduser()
    if not db_path.exists():
        raise SystemExit(f"Catalog database not found at {db_path}")

    result = similarity_threshold_module.compute_similarity_threshold(
        db_path,
        percentile=args.percentile,
        window_days=args.window_days,
    )

    print(
        f"similarity_threshold={result.threshold:.3f} samples={result.samples} "
        f"percentile={result.percentile:.2f} fallback={result.fallback_used}"
    )

    if args.output:
        payload = {
            "threshold": result.threshold,
            "samples": result.samples,
            "percentile": result.percentile,
            "fallback_used": result.fallback_used,
            "window_start_ms": result.window_start_ms,
            "window_end_ms": result.window_end_ms,
            "database": str(db_path.resolve()),
            "window_days": args.window_days,
        }
        write_output(args.output, payload)
        print(f"Wrote summary to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
