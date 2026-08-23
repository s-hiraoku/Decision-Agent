# AGENTS.md

## Cursor Cloud specific instructions

This is a single-product, stdlib-only Python CLI project (`decision-agent`) managed
with [uv](https://docs.astral.sh/uv/). There is no web frontend or database. The
product surface is the CLI under `src/decision_agent/`.

### Preferred review path: local-agent-gateway (`--engine llm`)

**Prefer the LLM review engine via [local-agent-gateway](https://github.com/s-hiraoku/local-agent-gateway).**
When exercising review / iterate / evaluate flows that involve judgment quality,
use `--engine llm` rather than the default `heuristic` engine. Do not silently
fall back to `heuristic` if the gateway call fails — surface the error.

Required configuration (see `README.md` / `docs/operation-guide.md`):

| Variable | Purpose |
| --- | --- |
| `DECISION_AGENT_GATEWAY_URL` | Gateway base URL (default `http://127.0.0.1:8787`) |
| `DECISION_AGENT_GATEWAY_TOKEN` | Owner bearer token (required for `--engine llm`) |
| `DECISION_AGENT_GATEWAY_TIMEOUT` | Optional polling timeout seconds (default `120`) |
| `DECISION_AGENT_GATEWAY_REPO` | Optional; only for older gateways that need coding runs |

Example:

```bash
export DECISION_AGENT_GATEWAY_URL="${DECISION_AGENT_GATEWAY_URL:-http://127.0.0.1:8787}"
export DECISION_AGENT_GATEWAY_TOKEN  # must be set from secrets / Keychain
PYTHONPATH=src uv run python -m decision_agent.cli review \
  examples/review-profile.json examples/review-request.json --engine llm
```

Cloud-agent caveat: the Gateway is normally a **loopback-only** service on the
owner's machine (macOS LaunchAgent). A Cloud Agent VM cannot reach the owner's
`127.0.0.1:8787`. Provide a Cloud-reachable `DECISION_AGENT_GATEWAY_URL` (for
example Tailscale / tunnel) plus `DECISION_AGENT_GATEWAY_TOKEN` as environment
secrets, or run the Gateway inside the agent environment. Confirm `GET /readyz`
succeeds before relying on `--engine llm`.

`heuristic` remains valid for unit tests, offline CI, and deterministic
regression checks that intentionally avoid the Gateway.

### Tooling notes

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
  - Preferred review (gateway): `--engine llm` as above
  - Offline review: omit `--engine` or pass `--engine heuristic`
- The `learn`/`iterate`/`evaluate` commands write append-only JSONL records and use
  atomic temp-file replacement for profile writes; point `--records`/`--output` at a
  scratch dir (e.g. `/tmp/...`) so example files under `examples/` stay clean.
