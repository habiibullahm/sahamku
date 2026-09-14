# Repository Guidelines

## Project Structure & Module Organization

`sahamku/` contains the application. Keep Telegram handlers in `bot/`, scheduled jobs in
`bot/scheduler.py`, data ingestion in `ingestion/`, and analytical reports in `analysis/`.
Technical indicators, rule signals, formatting, and SQLite access live in `indicators/`,
`signals/`, `report/`, and `db.py`. Use `scripts/` for repeatable manual jobs, data imports,
and deployment. Tests mirror features in `tests/`; keep assets under `assets/` and operational
documents under `docs/`.

## Build, Test, and Development Commands

Create a Python 3.12 environment and install development dependencies:

```bash
python -m venv .venv
pip install -e ".[dev]"
python -m sahamku.bot.main
```

Run the full suite with `pytest` and lint with `ruff check sahamku tests`.
Use `python scripts/run_job.py aftermarket` or `python scripts/run_job.py premarket` to inspect
reports without sending Telegram messages. Do not run local long polling while the Docker bot
uses the same Telegram token.

## Coding Style & Naming Conventions

Use Python 3.12, four-space indentation, type annotations for public functions, and lowercase
`snake_case` for modules, functions, and variables. Use `PascalCase` for classes and dataclasses.
Ruff enforces a 100-character line limit and `E`, `F`, `I`, `W`, and `UP` rules. Preserve HTML
escaping in Telegram text and keep every response within the formatter's 4,096-character limit.

## Testing Guidelines

Name files `test_<feature>.py` and tests `test_<behavior>`. Add focused fixtures for market-data
edge cases: stale observations, missing bars, zero volume, and partial provider responses. Run
the relevant test file first, then the complete `pytest` suite. Do not call live data providers
from tests.

## Commit, Pull Request, and Deployment Guidelines

Use concise imperative commits such as `feat: add cached intraday snapshots`, `fix: escape
Telegram labels`, or `chore: rename VPS alias`. Keep changes focused; do not commit `.env`,
SQLite databases, charts, credentials, or local archives. Describe user-visible behavior and
test results in pull requests.

Deploy committed `main` changes with `bash scripts/deploy.sh` after tests pass. The script sends
the current Git archive to `bot-vps`, rebuilds Docker, and restarts the bot. Verify polling and
recent logs afterward; never modify `/opt/sahamku/.env` through a code deployment.
