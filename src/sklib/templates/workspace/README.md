# KiCad component library

This library uses SKLib with Git-backed TOML records.

```console
uv sync
uv run sklib doctor
uv run sklib web
```

Validate and build before committing:

```console
uv run sklib check
uv run sklib build
```

Commit `parts/`, `types/`, and reviewed files under `kicad/`. Do not commit
`generated/`, `.sklib/`, `.env`, pricing, stock data, or supplier API dumps.
