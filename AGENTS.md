# AGENTS.md - SKLib development guide

SKLib is a Git-backed KiCad DBLib component-library framework. Canonical parts
are per-part TOML files. Declarative TOML type definitions drive validation,
web forms, and SQLite columns. SQLite DBLib files are generated artifacts.

## Project structure

```text
sklib/
├── parts/                  # Canonical part records
├── types/                  # Declarative component-type definitions
├── kicad/                  # Reviewed symbols, footprints, and 3D models
├── generated/              # Local build artifacts, ignored
├── src/sklib/
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── type_definitions.py
│   ├── store.py
│   ├── build.py
│   ├── kicad/
│   ├── suppliers/
│   └── web/
├── tests/
├── sklib.toml
└── justfile                # Optional command shortcuts
```

## Commands

```console
uv sync --locked
uv run sklib doctor
uv run sklib check
uv run sklib build
uv run sklib index
uv run sklib web
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

Optional equivalents:

```console
just install
just check
just web
```

CLI commands are canonical because `just` is optional and must not be required
on Windows.

## Architectural rules

- TOML under `parts/` is sole component-data source.
- Pydantic models define stable record structure.
- `types/*.toml` defines type-specific specification fields.
- Never add CSV compatibility or a second authoring database.
- Never update generated SQLite incrementally; rebuild from canonical records.
- Never commit `generated/`, `.sklib/`, credentials, API dumps, price, or stock.
- Keep supplier results advisory and require human review.
- Use `Workspace` for paths; do not depend on current working directory.
- Use atomic replacement for TOML and DBLib config writes.
- Build SQLite in temporary file, then publish through SQLite backup into stable
  database file so KiCad's open ODBC connection sees changes.
- Keep implementation explicit; avoid plugin systems and abstraction layers
  without demonstrated need.

## Code style

- Python 3.13+
- 88-character lines
- Four spaces, no tabs
- Type hints for every function parameter and return
- Imports ordered as standard library, third party, local
- `snake_case` functions and variables
- `PascalCase` classes
- `SCREAMING_SNAKE_CASE` constants
- Google-style docstrings where documentation is useful
- No comments unless explicitly required
- `Path` for paths
- UTF-8 and explicit newline behavior for file operations
- User-facing failures need actionable messages

## Testing

- Unit tests for models and type definitions
- Filesystem tests use pytest `tmp_path`
- Web tests use FastAPI `TestClient` and temporary workspaces
- Supplier tests use sanitized fixtures and never call live APIs
- KiCad parser tests use tiny fixture libraries
- Test behavior and generated SQLite contents, not implementation details
- Keep tests independent of installed KiCad and ODBC drivers
- Run full baseline before finishing:

```console
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run sklib check
uv run sklib build
uv build
```

Cross-platform CI must cover Ubuntu, macOS, and Windows. Actual KiCad/ODBC
integration remains a documented manual smoke test on each operating system.

## Canonical part layout

```text
parts/<component_type>/<ID>.toml
```

New IDs use the matching type prefix plus two groups of five random Crockford
Base32 characters; legacy numeric IDs remain valid. Filename must equal ID.
Parent directory must equal component type. Manufacturer and MPN pairs are
unique case-insensitively.

See `docs/data-format.md` and `docs/design.md` before changing data structures.
