# Unit Test Conventions

All module-scoped unit tests live in this directory so developers can run `pytest`
without juggling multiple discovery paths. Mirror the source tree with subfolders
(e.g., `tests/unit/catalog/`) and import shared fixtures from `tests.conftest`
when needed. Keep unit suites fast and isolated; integration or regression
scenarios belong in the sibling directories.
