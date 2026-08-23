# AGENTS.md

## Cursor Cloud specific instructions

This is a single-product, stdlib-only Python CLI project (`decision-agent`) managed
with [uv](https://docs.astral.sh/uv/). There are no servers, databases, or web
frontends to run — everything runs as a local CLI process. The one external service
(`local-agent-gateway`) is strictly optional and only used with `--engine llm`; it is
not required for any tests or default usage.

Non-obvious notes:

- `uv` is installed to `~/.local/bin` (on `PATH` via the startup update script). If a
  fresh shell cannot find `uv`, run `export PATH="$HOME/.local/bin:$PATH"`.
- `uv sync` provisions its own managed Python (currently 3.14) into `.venv`, even
  though `pyright`/`pyproject.toml` target `pythonVersion = "3.11"`. That mismatch is
  expected and harmless.
- The package lives under `src/`, so CLI/tests must run with `PYTHONPATH=src`.
- Standard commands are documented in `README.md` and `.github/workflows/ci.yml`. In
  short:
  - Lint/type-check: `uv run pyright`
  - Tests: `PYTHONPATH=src uv run python -m unittest discover -s tests`
  - Run the core review CLI: `PYTHONPATH=src uv run python -m decision_agent.cli review examples/review-profile.json examples/review-request.json`
- The `learn`/`iterate`/`evaluate` commands write append-only JSONL records and use
  atomic temp-file replacement for profile writes; point `--records`/`--output` at a
  scratch dir (e.g. `/tmp/...`) so example files under `examples/` stay clean.
