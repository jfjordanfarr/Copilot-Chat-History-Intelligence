# Test Suite Overview

This directory hosts the shared regression and integration tests exercised by the
Copilot Recall Vision feature. Key conventions:

- **Fixtures** live in `conftest.py`. The `workspace_root` fixture resolves to the
  repository root so tests can load sample data files without hard-coded relative
  paths. Use `sample_catalog_path` when a test needs a writable SQLite catalog –
  it transparently prefers the real workspace catalog and falls back to a
temporary copy when no catalog is present.
- **Helpers** live under `helpers/`. The `catalog_builder` module synthesises
  raw Copilot chat sessions and lays them out in the same directory structure as
  VS Code's global storage, keeping ingestion-focused tests concise.
- **All suites (unit, integration, regression)** now live under this top-level
  `tests/` directory to keep discovery simple. Module-specific tests should
  import fixtures from `tests.conftest` as needed rather than defining
  package-local `pytest_plugins` shims.

Run `pytest` from the repo root to execute every test suite, or target
`tests/integration/` and `tests/regression/` when you only need the higher-level
checks.
