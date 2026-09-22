# Manual verification

Use this checklist after changes affecting storage, forms, builds, or setup.

## Automated baseline

Run from repository root:

```console
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run sklib check
uv run sklib build
uv build
uv run python scripts/smoke_workspace.py
```

Expected results:

- All tests pass.
- Catalog reports two parts and three component types.
- Build reports three SQLite tables.
- `generated/sklib.db` and `generated/sklib.kicad_dbl` exist.
- `git status` does not show generated files.

## Isolated workspace

Test the built wheel through the same initialization and installation path used
by a consumer. Keep the workspace for inspection:

```console
uv build
uv run python scripts/smoke_workspace.py --workspace ../sklib-manual-test
cd ../sklib-manual-test
uv run sklib web
```

The smoke test installs the wheel, initializes the workspace, validates the
empty catalog, and builds its DBLib artifacts.

Open <http://127.0.0.1:8000>.

1. Open each passive form and confirm fields differ by type.
2. Search `Device`, select library result, then choose `C_small`.
3. Verify arrows and `Ctrl+N`/`Ctrl+P` navigate open search results.
4. Repeat library filtering with footprint picker.
5. Add capacitor with valid `Library:Name` symbol and footprint.
6. Confirm success message includes saved ID and build time.
7. Open, edit, and save part.
8. Try creating same manufacturer and MPN again; expect duplicate error.
9. Enter malformed symbol such as `Device-C`; expect field error and retained data.
10. Delete test part; confirm it disappears and database rebuild succeeds.
11. Stop server with Ctrl+C.

Inspect workspace afterward:

```text
parts/capacitor/CAP-XXXXX-XXXXX.toml
```

A successful edit changes one readable TOML file. `.sklib/` and `generated/`
remain ignored.

## KiCad integration

On each supported operating system:

1. Install SQLite ODBC driver.
2. Run `uv run sklib doctor` and `uv run sklib build`.
3. Add generated `.kicad_dbl` in KiCad's database-library manager.
4. Open symbol chooser and find test capacitor and resistor.
5. Search by exact MPN, then repeat without MPN punctuation.
6. Verify value, footprint, MPN, manufacturer, status, and datasheet.
7. Keep KiCad open, edit a part in web UI, and verify rebuild behavior.

Record KiCad version, OS version, ODBC driver name, and any required setup.
The open-KiCad rebuild check is especially important on Windows because file
locking differs from Linux and macOS.

## DigiKey integration

Only run when credentials are available in ignored `.env`:

1. Enter exact passive MPN.
2. Search DigiKey.
3. Select matching result.
4. Confirm current stock, MOQ, and packaging appear.
5. Confirm imported values appear without changing component type silently.
6. Change one populated field and search again; confirm overwrite prompt.
7. Review all values before saving.

Normal editing must still work when `.env` is absent.
