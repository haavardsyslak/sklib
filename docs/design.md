# SKLib design

## Scope

SKLib maintains atomic manufacturer parts for KiCad database libraries. Included
component types are capacitors, connectors, inductors, and resistors.

TOML part records, reviewed native KiCad assets, and declared KiCad generator
inputs are source data. SQLite databases, DBLib configuration files, drafts,
and visual review output are local build artifacts. Generators accelerate draft
creation; KiCad editors remain normal authoring tools. Git provides history,
review, and releases.

SKLib is local-first. A future hosted editor may create Git commits or pull
requests, but must not introduce a second canonical authoring database.

## Contributor workflow

```text
pull repository
    -> run local web editor
    -> search existing parts
    -> enter MPN or fetch supplier suggestion
    -> review metadata
    -> select symbol and footprint
    -> validate and save one TOML record
    -> rebuild local DBLib
    -> review Git diff
    -> commit and open pull request
```

Supplier results are suggestions. Users confirm imported metadata and KiCad
mapping. Core editing works without internet or supplier credentials.

## Data flow

```text
Web UI ----\
            -> Catalog -> parts/<type>/<ID>.toml
CLI -------/                 |
                              -> deterministic builder
                                      |
                                      +-> generated/sklib.db
                                      +-> generated/sklib.kicad_dbl
```

## Invariants

- TOML is sole component-data source.
- Reviewed native KiCad files are canonical library assets.
- Pydantic validates stable record structure.
- `types/*.toml` defines component-specific fields and forms.
- Unknown record and specification fields fail validation.
- New specification fields are declared in `types/*.toml`.
- Filename and directory match component ID and type.
- IDs are globally unique and never reused intentionally.
- Manufacturer and MPN pairs are unique, case-insensitively.
- TOML and DBLib configuration writes use atomic replacement.
- Every database build starts from canonical source files.
- Validated temporary database is transactionally copied into stable generated
  file so existing KiCad ODBC connections can observe changes.
- Local drafts, databases, review output, and machine-specific paths are never
  committed.
- Review state belongs to Git; manufacturer lifecycle belongs to part data.

## Deliberate non-goals for first release

- Inventory, pricing, or ERP behavior
- A universal symbol, footprint, or 3D-model generator
- Hosted authentication and authorization
- Automatic Git commits
- Schema plugins or executable project configuration
- Compatibility with legacy CSV data
