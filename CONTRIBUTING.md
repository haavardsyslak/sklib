# Contributing

## Setup

```console
uv sync --locked
uv run sklib doctor
```

`just` is optional. Python and CLI commands remain canonical on every platform.

## Before submitting

```console
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run sklib check
uv run sklib build
uv build
uv run python scripts/smoke_workspace.py
```

For UI or build changes, follow [`docs/manual-testing.md`](docs/manual-testing.md).

## Component changes

- Add one atomic manufacturer part per TOML file.
- Use web editor when convenient; hand editing remains supported.
- Do not commit `generated/` or `.sklib/`.
- Do not commit prices, stock levels, credentials, or supplier response dumps.
- Prefer one component or closely related set per pull request.
- Explain symbol and footprint choices when not obvious.
- Verify every pin and mechanical dimension against the manufacturer datasheet.

## Type-definition changes

Normal specification fields belong in `types/*.toml`. A type-definition change
must keep every existing part valid or update affected records in same pull
request. Avoid adding fields until representative real parts demonstrate need.

## Code changes

- Keep implementation small and explicit.
- Add type hints to all function parameters and returns.
- Add tests for behavior, not internal implementation.
- Use temporary workspaces and sanitized supplier fixtures.
- Never call live supplier APIs from automated tests.
