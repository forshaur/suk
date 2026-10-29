# Agent Guide

`suk` is a Python disposable temp-mail SDK and terminal CLI. Keep changes small and keep the SDK free of terminal and file I/O.

## Commands

- Install for development: `pip install -e ".[dev]"`
- Run tests: `pytest -q`
- Build wheel: `python -m pip wheel . --no-deps -w /tmp/suk-wheel`
- Run CLI from source: `python -m suk --help`

## Important behavior

- Plain `suk` opens a blocking terminal UI only when stdin and stdout are terminals. In CI or from an agent it prints one snapshot and exits.
- Destructive commands require `--yes`: `suk delete --slot N --yes`, `suk --shred all --yes`.
- State lives in `$HOME` by default. `SUK_HOME=/path` isolates sessions and history. Files are written atomically with mode `0600`; `SUK_HOME` is created with mode `0700`.
- The update checker only prints a notice. It must never run `pip install`.
- The CLI must not import or duplicate HTTP logic from `suk/client.py`. Use `Mailbox`.

## Output contract

- Human output goes to stdout. Status and errors go to stderr.
- `--json` emits exactly one JSON document on stdout with keys `schema_version`, `ok`, `data`, `error`, `meta`. In JSON mode, errors are part of that document, not separate stderr text.
- Exit codes: `0` success, `2` usage, `3` auth, `4` not found, `5` rate limit, `6` network, `7` API, `130` interrupted.

## Tests

Tests must not touch the network or the real home directory. Use fake `curl_cffi` responses and the `SUK_HOME` fixture in `tests/conftest.py`.
