"""Compatibility shim preserving the historical `chat_logs_to_sqlite` module path."""

from __future__ import annotations

import sys

import catalog.ingest as _catalog_ingest

__all__ = [name for name in dir(_catalog_ingest) if not name.startswith("_")]

for _name in __all__:
    globals()[_name] = getattr(_catalog_ingest, _name)

del _name

UserVisibleError = _catalog_ingest.UserVisibleError
main = _catalog_ingest.main


def __getattr__(name: str):
    return getattr(_catalog_ingest, name)


def __dir__():
    return sorted(set(__all__) | set(globals().keys()))


if __name__ == "__main__":
    try:
        main()
    except UserVisibleError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
