# SKLib

Git-backed KiCad DBLib component library with a local web editor.

SKLib stores one atomic manufacturer part per TOML file. It validates the
catalog and builds a SQLite database for KiCad. Included component types are
capacitors, connectors, inductors, and resistors.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- KiCad 10 or newer
- SQLite ODBC driver for KiCad DBLib use

Development and editing work on Linux, macOS, and Windows. `just` is optional.

## Setup

```console
uv sync
uv run sklib doctor
uv run sklib check
uv run sklib build
uv run sklib web
```

Open <http://127.0.0.1:8000>. The web editor works without internet access.
DigiKey lookup is optional.

Equivalent optional shortcuts:

```console
just install
just check
just web
```

## Component workflow

1. Pull latest Git revision.
2. Start `uv run sklib web`.
3. Search for existing manufacturer part number.
4. Add component manually or fetch DigiKey suggestions.
5. Review metadata and select KiCad symbol and footprint.
6. Save and verify generated DBLib.
7. Review changed TOML file with `git diff`.
8. Commit and open pull request.

Canonical records live at:

```text
parts/<component_type>/<ID>.toml
```

New IDs use locally generated Crockford Base32 values such as
`RES-7K3MP-9QWX2`, so contributors do not coordinate sequence numbers. Legacy
numeric IDs remain valid.

Generated files live under `generated/` and are ignored by Git.

## Commands

```console
uv run sklib check
uv run sklib build
uv run sklib doctor
uv run sklib index
uv run sklib new-id capacitor
uv run sklib web
```

Use another workspace from any directory:

```console
uv run sklib --workspace /path/to/library check
```

Create a new library after SKLib is published or installed:

```console
uvx sklib init my-library
```

## Component types

Type definitions are declarative TOML files under `types/`. They drive
validation, forms, ID prefixes, and generated SQLite columns. Adding a normal
field does not require Python changes.

```toml
schema_version = 1
name = "capacitor"
label = "Capacitor"
plural = "Capacitors"
prefix = "CAP"
value_field = "capacitance"
default_symbol = "Device:C_Small"

[[fields]]
name = "capacitance"
label = "Capacitance"
kind = "string"
required = true
```

Supported field kinds are `string`, `integer`, `number`, `boolean`, and `enum`.

## DigiKey

Create an ignored `.env` file in the workspace:

```dotenv
DIGIKEY_CLIENT_ID=...
DIGIKEY_CLIENT_SECRET=...
```

Missing credentials only disable searches; normal editing remains available.
Current stock, MOQ, and packaging are shown during selection but are not stored
in canonical TOML.

## Add library to KiCad

1. Install a SQLite ODBC driver.
2. Build library:

   ```console
   uv run sklib build
   ```

3. Open KiCad.
4. Select **Preferences → Manage Symbol Libraries**.
5. Open **Database Libraries** tab.
6. Click **Add existing library** and select:

   ```text
   <workspace>/generated/sklib.kicad_dbl
   ```

7. Click **OK**. Parts now appear in symbol chooser under library type names.

The chooser can find parts by SKLib ID, exact MPN, punctuation-free MPN,
manufacturer, or canonical keywords. MPN remains a chooser column but does not
need to be visible for keyword search.

If KiCad reports missing ODBC driver, set driver name in ignored `.env`, rebuild,
and add library again:

```dotenv
SKLIB_ODBC_DRIVER=SQLite3 ODBC Driver
```

Run `uv run sklib doctor` to inspect selected paths and driver. Rebuild after
moving workspace because generated DBLib contains absolute database path.

## Development checks

```console
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run sklib check
uv run sklib build
uv build
uv run python scripts/smoke_workspace.py
```

Consumer smoke test builds a disposable library from installed wheel. Pass
`--workspace PATH` to keep it for manual inspection.

See [`docs/design.md`](docs/design.md) for architectural rules,
[`docs/data-format.md`](docs/data-format.md) for canonical records, and
[`docs/manual-testing.md`](docs/manual-testing.md) for human verification.
Contributions follow [`CONTRIBUTING.md`](CONTRIBUTING.md).
