#!/usr/bin/env python3
"""
Build SQLite database from CSV part files.

Usage:
    python build_db.py [--output PATH] [--dbl PATH] [CSV_FILES...]

If no CSV files are specified, processes all CSVs in src/parts/
"""

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

SCHEMA_DIR = Path(__file__).parent.parent / "src" / "schema"


def load_schema() -> tuple[list[str], dict[str, list[str]]]:
    """Return (base_columns, type_fields_by_plural).

    base_columns: ordered column names from src/schema/base.json
    type_fields_by_plural: maps csv filename stem (e.g. "capacitors") to the
        list of type-specific field names from the matching type file.
    """
    with open(SCHEMA_DIR / "base.json", encoding="utf-8") as f:
        base = json.load(f)
    base_columns = list(base["columns"].keys())

    type_fields_by_plural: dict[str, list[str]] = {}
    for fp in (SCHEMA_DIR / "types").glob("*.json"):
        with open(fp, encoding="utf-8") as f:
            type_data = json.load(f)
        plural = type_data.get("plural", type_data["name"] + "s")
        type_fields_by_plural[plural] = [f["name"] for f in type_data.get("fields", [])]

    return base_columns, type_fields_by_plural


def schema_columns_for(table_name: str, base_columns: list[str], type_fields: dict[str, list[str]]) -> list[str]:
    """Canonical column list for a table: base columns ∪ type-specific fields."""
    cols = list(base_columns)
    seen = set(cols)
    for name in type_fields.get(table_name, []):
        if name not in seen:
            cols.append(name)
            seen.add(name)
    return cols


def create_table(conn: sqlite3.Connection, table_name: str, columns: list[str]):
    """Create a table with the given columns."""
    col_defs = ", ".join(f'"{col}" TEXT' for col in columns)
    conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    conn.execute(f'CREATE TABLE "{table_name}" ({col_defs})')

    conn.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_id" ON "{table_name}" ("id")'
    )
    conn.execute(
        f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_mpn" ON "{table_name}" ("mpn")'
    )


def import_csv(
    conn: sqlite3.Connection,
    csv_path: Path,
    base_columns: list[str],
    type_fields: dict[str, list[str]],
) -> int:
    """Import a CSV file into the database. Returns row count.

    Table columns come from the schema, not the CSV header — this keeps the
    DB shape consistent across rebuilds even if a CSV is missing/extra fields.
    Unknown CSV columns are skipped with a warning.
    """
    table_name = csv_path.stem
    columns = schema_columns_for(table_name, base_columns, type_fields)
    create_table(conn, table_name, columns)

    placeholders = ", ".join("?" for _ in columns)
    col_names = ", ".join(f'"{col}"' for col in columns)
    insert_sql = f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders})'

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            return 0

        unknown = [c for c in reader.fieldnames if c not in columns]
        if unknown:
            print(
                f"[build] {csv_path.name}: ignoring CSV columns not in schema: "
                f"{', '.join(unknown)}",
                file=sys.stderr,
            )

        row_count = 0
        for row in reader:
            values = [row.get(col, "") for col in columns]
            conn.execute(insert_sql, values)
            row_count += 1

        return row_count


def generate_dbl_config(tables: list[str], db_path: Path, dbl_path: Path):
    """Generate the KiCad .kicad_dbl configuration file."""

    # Field definitions common to all tables
    # Note: description and keywords are handled via 'properties' section
    # to properly populate KiCad's built-in symbol properties
    common_fields = [
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
            "column": "status",
            "name": "Status",
            "visible_on_add": False,
            "visible_in_chooser": True,
            "show_name": True,
        },
    ]

    # Properties map built-in KiCad symbol properties to database columns
    common_properties = {
        "description": "description",
        "keywords": "keywords",
        "exclude_from_bom": "exclude_from_bom",
    }

    # Build library entries for each table
    libraries = []
    for table in sorted(tables):
        # Convert table name to display name (e.g., "capacitors" -> "Capacitors")
        display_name = table.replace("_", " ").title()

        libraries.append(
            {
                "name": display_name,
                "table": table,
                "key": "id",
                "symbols": "symbol",
                "footprints": "footprint",
                "fields": common_fields,
                "properties": common_properties,
            }
        )

    # Use absolute path to the database
    db_absolute_path = str(db_path.resolve())

    config = {
        "meta": {"version": 0},
        "name": "SKLib Parts",
        "description": "Atomic parts library with manufacturer-specific components",
        "source": {
            "type": "odbc",
            "dsn": "",
            "connection_string": f"Driver=SQLite3;Database={db_absolute_path}",
        },
        "libraries": libraries,
    }

    with open(dbl_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


def main():
    parser = argparse.ArgumentParser(description="Build SQLite database from CSV files")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path(__file__).parent.parent / "generated" / "sklib.db",
        help="Output SQLite database path",
    )
    parser.add_argument(
        "--dbl",
        type=Path,
        default=Path(__file__).parent.parent / "kicad" / "sklib.kicad_dbl",
        help="Output .kicad_dbl configuration path",
    )
    parser.add_argument(
        "--no-dbl",
        action="store_true",
        help="Skip generating .kicad_dbl file",
    )
    parser.add_argument(
        "csv_files",
        type=Path,
        nargs="*",
        help="CSV files to import (default: src/parts/*.csv)",
    )

    args = parser.parse_args()

    # Find CSV files
    if args.csv_files:
        csv_files = args.csv_files
    else:
        parts_dir = Path(__file__).parent.parent / "src" / "parts"
        csv_files = sorted(parts_dir.glob("*.csv"))

    if not csv_files:
        print("No CSV files found", file=sys.stderr)
        return 1

    # Ensure output directory exists
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing database
    if args.output.exists():
        args.output.unlink()

    # Create database and import CSVs
    tables = []
    total_rows = 0

    print(f"[build] Creating {args.output}...")

    base_columns, type_fields = load_schema()

    with sqlite3.connect(args.output) as conn:
        for csv_path in csv_files:
            row_count = import_csv(conn, csv_path, base_columns, type_fields)
            table_name = csv_path.stem
            tables.append(table_name)
            total_rows += row_count
            print(f"[build] Table '{table_name}': {row_count} rows")

        conn.commit()

    # Generate .kicad_dbl config
    if not args.no_dbl:
        generate_dbl_config(tables, args.output, args.dbl)
        print(f"[build] Generated {args.dbl}")

    # Print summary
    db_size = args.output.stat().st_size
    size_str = f"{db_size / 1024:.1f} KB" if db_size >= 1024 else f"{db_size} B"
    print(f"[build] Done: {total_rows} parts in {len(tables)} tables ({size_str})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
