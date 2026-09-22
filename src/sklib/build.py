import json
import os
import re
import sqlite3
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sklib.config import Workspace
from sklib.models import Part
from sklib.store import Catalog
from sklib.type_definitions import ComponentTypeDefinition

_COMMON_DBL_FIELDS = [
    {
        "column": "mpn",
        "name": "MPN",
        "visible_on_add": False,
        "visible_in_chooser": True,
        "show_name": True,
    },
    {
        "column": "manufacturer",
        "name": "Manufacturer",
        "visible_on_add": False,
        "visible_in_chooser": True,
        "show_name": True,
    },
    {
        "column": "value",
        "name": "Value",
        "visible_on_add": True,
        "visible_in_chooser": True,
        "show_name": False,
    },
    {
        "column": "package",
        "name": "Package",
        "visible_on_add": False,
        "visible_in_chooser": True,
        "show_name": True,
    },
    {
        "column": "datasheet",
        "name": "Datasheet",
        "visible_on_add": False,
        "visible_in_chooser": False,
    },
    {
        "column": "manufacturer_status",
        "name": "Status",
        "visible_on_add": False,
        "visible_in_chooser": True,
        "show_name": True,
    },
]

_BASE_COLUMNS = [
    "id",
    "component_type",
    "mpn",
    "manufacturer",
    "description",
    "value",
    "package",
    "symbol",
    "footprint",
    "datasheet",
    "keywords",
    "search_terms",
    "manufacturer_status",
    "notes",
    "exclude_from_bom",
    "supplier",
    "supplier_sku",
    "supplier_url",
]


class BuildError(RuntimeError):
    """Raised when DBLib artifacts cannot be safely published."""


@dataclass(frozen=True)
class BuildResult:
    """Paths and counts produced by a successful catalog build."""

    database_path: Path
    dbl_path: Path
    part_count: int
    table_count: int
    elapsed_seconds: float


def build_catalog(workspace: Workspace) -> BuildResult:
    """Validate catalog and transactionally rebuild KiCad DBLib artifacts."""
    started = time.perf_counter()
    catalog = Catalog(workspace)
    parts = catalog.load_all()
    by_type: dict[str, list[Part]] = defaultdict(list)
    for part in parts:
        by_type[part.component_type].append(part)

    workspace.generated_dir.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=workspace.generated_dir, prefix=".sklib.", suffix=".db"
    )
    os.close(descriptor)
    temporary_database = Path(temporary_name)

    definitions = sorted(catalog.types, key=lambda item: item.name)
    try:
        with sqlite3.connect(temporary_database) as connection:
            for definition in definitions:
                _build_table(
                    connection,
                    definition,
                    sorted(by_type[definition.name], key=lambda part: part.id),
                )
            connection.commit()
        _publish_database(temporary_database, workspace.database_path)
    except Exception:
        temporary_database.unlink(missing_ok=True)
        raise

    _write_dbl(workspace, definitions)
    return BuildResult(
        database_path=workspace.database_path,
        dbl_path=workspace.dbl_path,
        part_count=len(parts),
        table_count=len(definitions),
        elapsed_seconds=time.perf_counter() - started,
    )


def _build_table(
    connection: sqlite3.Connection,
    definition: ComponentTypeDefinition,
    parts: list[Part],
) -> None:
    table = _table_name(definition)
    columns = _columns(definition)
    definitions = [
        f'"{column}" TEXT PRIMARY KEY' if column == "id" else f'"{column}" TEXT'
        for column in columns
    ]
    connection.execute(f'CREATE TABLE "{table}" ({", ".join(definitions)})')
    connection.execute(f'CREATE INDEX "idx_{table}_mpn" ON "{table}" ("mpn")')

    placeholders = ", ".join("?" for _ in columns)
    names = ", ".join(f'"{column}"' for column in columns)
    statement = f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})'
    for part in parts:
        row = _flatten_part(part, definition)
        connection.execute(statement, [_cell(row.get(column)) for column in columns])


def _columns(definition: ComponentTypeDefinition) -> list[str]:
    columns = list(_BASE_COLUMNS)
    for field in definition.fields:
        if field.name not in columns:
            columns.append(field.name)
    return columns


def _flatten_part(part: Part, definition: ComponentTypeDefinition) -> dict[str, object]:
    supplier = part.suppliers[0] if part.suppliers else None
    row: dict[str, object] = {
        "id": part.id,
        "component_type": part.component_type,
        "mpn": part.mpn,
        "manufacturer": part.manufacturer,
        "description": part.description,
        "value": (
            part.mpn
            if definition.value_field == "mpn"
            else part.specs[definition.value_field]
        ),
        "symbol": part.kicad.symbol,
        "footprint": part.kicad.footprint,
        "datasheet": part.datasheet,
        "keywords": " ".join(part.keywords),
        "search_terms": _search_terms(part),
        "manufacturer_status": part.manufacturer_status,
        "notes": part.notes,
        "exclude_from_bom": part.kicad.exclude_from_bom,
        "supplier": supplier.name if supplier else "",
        "supplier_sku": supplier.sku if supplier else "",
        "supplier_url": supplier.product_url if supplier else "",
    }
    row.update(part.specs)
    return row


def _search_terms(part: Part) -> str:
    normalized_mpn = re.sub(r"[^A-Za-z0-9]+", "", part.mpn)
    candidates = [
        part.id,
        part.mpn,
        normalized_mpn,
        part.manufacturer,
        *part.keywords,
    ]
    terms: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.casefold()
        if candidate and normalized not in seen:
            terms.append(candidate)
            seen.add(normalized)
    return " ".join(terms)


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _table_name(definition: ComponentTypeDefinition) -> str:
    return f"{definition.name}s"


def _dbl_fields(definition: ComponentTypeDefinition) -> list[dict[str, object]]:
    fields = [dict(item) for item in _COMMON_DBL_FIELDS]
    existing = {str(item["column"]) for item in fields}
    for field in definition.fields:
        if field.name in existing or field.name == definition.value_field:
            continue
        fields.append(
            {
                "column": field.name,
                "name": field.label,
                "visible_on_add": False,
                "visible_in_chooser": True,
                "show_name": True,
            }
        )
    return fields


def _write_dbl(
    workspace: Workspace, definitions: list[ComponentTypeDefinition]
) -> None:
    libraries = []
    for definition in definitions:
        libraries.append(
            {
                "name": definition.plural,
                "table": _table_name(definition),
                "key": "id",
                "symbols": "symbol",
                "footprints": "footprint",
                "fields": _dbl_fields(definition),
                "properties": {
                    "description": "description",
                    "keywords": "search_terms",
                    "exclude_from_bom": "exclude_from_bom",
                },
            }
        )

    document = {
        "meta": {"version": 0},
        "name": workspace.name,
        "description": workspace.description,
        "source": {
            "type": "odbc",
            "dsn": "",
            "connection_string": (
                f"Driver={workspace.odbc_driver()};"
                f"Database={workspace.database_path.resolve()}"
            ),
        },
        "libraries": libraries,
    }
    content = json.dumps(document, indent=4, ensure_ascii=False) + "\n"
    if workspace.dbl_path.is_file():
        try:
            if workspace.dbl_path.read_text(encoding="utf-8") == content:
                return
        except OSError:
            pass
    descriptor, temporary_name = tempfile.mkstemp(
        dir=workspace.generated_dir, prefix=".sklib.", suffix=".kicad_dbl"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        _replace_artifact(temporary, workspace.dbl_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _publish_database(temporary: Path, destination: Path) -> None:
    if not destination.exists():
        _replace_artifact(temporary, destination)
        return

    deadline = time.monotonic() + 5

    def check_lock(status: int, remaining: int, total: int) -> None:
        del remaining, total
        if status in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            if time.monotonic() >= deadline:
                raise BuildError(
                    f"Cannot update {destination} because another program has "
                    "locked it. Close KiCad's symbol chooser, then build again."
                )

    try:
        with (
            sqlite3.connect(temporary) as source,
            sqlite3.connect(destination, timeout=5) as target,
        ):
            source.backup(target, pages=128, progress=check_lock, sleep=0.05)
    except sqlite3.Error as error:
        raise BuildError(f"Cannot update {destination}: {error}") from error
    finally:
        temporary.unlink(missing_ok=True)


def _replace_artifact(temporary: Path, destination: Path) -> None:
    try:
        temporary.replace(destination)
    except PermissionError as error:
        raise BuildError(
            f"Cannot replace {destination}. Close KiCad or other programs using it, "
            "then build again."
        ) from error
