#!/usr/bin/env python3
"""
Validate CSV part files against the schema.

Usage:
    python validate.py [--schema PATH] [CSV_FILES...]

If no CSV files are specified, validates all CSVs in src/parts/
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path


def load_schema(schema_dir: Path) -> dict:
    """Load and return the schema definition from split files."""
    base_path = schema_dir / "base.json"
    with open(base_path) as f:
        schema = json.load(f)

    types_dir = schema_dir / "types"
    component_types = {}
    for fp in types_dir.glob("*.json"):
        with open(fp) as f:
            type_data = json.load(f)
            component_types[type_data["name"]] = type_data

    return {
        "columns": schema["columns"],
        "id_prefixes": schema["id_prefixes"],
        "common_symbols": schema["common_symbols"],
        "common_footprints": schema["common_footprints"],
        "component_types": component_types,
    }


def validate_row(row: dict, schema: dict, row_num: int, filename: str) -> list[str]:
    """Validate a single row against the schema. Returns list of errors."""
    errors = []
    columns = schema["columns"]

    for col_name, col_def in columns.items():
        value = row.get(col_name, "").strip()

        # Check required fields
        if col_def.get("required") and not value:
            errors.append(f"{filename}:{row_num}: Missing required field '{col_name}'")
            continue

        # Skip further validation if empty and not required
        if not value:
            continue

        # Check pattern
        if "pattern" in col_def:
            if not re.match(col_def["pattern"], value):
                errors.append(
                    f"{filename}:{row_num}: Field '{col_name}' value '{value}' "
                    f"does not match pattern '{col_def['pattern']}'"
                )

        # Check enum
        if "enum" in col_def:
            if value not in col_def["enum"]:
                errors.append(
                    f"{filename}:{row_num}: Field '{col_name}' value '{value}' "
                    f"must be one of: {', '.join(col_def['enum'])}"
                )

    # Check for unexpected columns
    expected_cols = set(columns.keys())
    actual_cols = set(row.keys())
    unexpected = actual_cols - expected_cols
    if unexpected:
        errors.append(
            f"{filename}:{row_num}: Unexpected columns: {', '.join(sorted(unexpected))}"
        )

    return errors


def validate_csv(
    csv_path: Path, schema: dict, all_ids: set
) -> tuple[list[str], list[str], int]:
    """
    Validate a CSV file against the schema.

    Returns:
        (errors, warnings, row_count)
    """
    errors = []
    warnings = []
    row_count = 0
    seen_ids = set()
    seen_mpns = set()

    filename = csv_path.name

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            # Check header
            if reader.fieldnames is None:
                errors.append(f"{filename}: Empty or invalid CSV file")
                return errors, warnings, 0

            expected_cols = set(schema["columns"].keys())
            actual_cols = set(reader.fieldnames)

            missing_cols = expected_cols - actual_cols
            if missing_cols:
                errors.append(
                    f"{filename}: Missing columns: {', '.join(sorted(missing_cols))}"
                )

            for row_num, row in enumerate(
                reader, start=2
            ):  # Start at 2 (header is row 1)
                row_count += 1

                # Validate row against schema
                row_errors = validate_row(row, schema, row_num, filename)
                errors.extend(row_errors)

                # Check ID uniqueness within file
                part_id = row.get("id", "").strip()
                if part_id:
                    if part_id in seen_ids:
                        errors.append(
                            f"{filename}:{row_num}: Duplicate ID '{part_id}' within file"
                        )
                    elif part_id in all_ids:
                        errors.append(
                            f"{filename}:{row_num}: Duplicate ID '{part_id}' (exists in another file)"
                        )
                    else:
                        seen_ids.add(part_id)
                        all_ids.add(part_id)

                # Warn on duplicate MPNs (not an error, same part might be listed twice intentionally)
                mpn = row.get("mpn", "").strip()
                if mpn:
                    if mpn in seen_mpns:
                        warnings.append(f"{filename}:{row_num}: Duplicate MPN '{mpn}'")
                    seen_mpns.add(mpn)

    except Exception as e:
        errors.append(f"{filename}: Failed to read file: {e}")

    return errors, warnings, row_count


def get_next_id(csv_path: Path, schema: dict) -> str:
    """Get the next available ID for a category."""
    category = csv_path.stem
    prefix = schema.get("id_prefixes", {}).get(category)

    if not prefix:
        # Try to infer from existing IDs
        prefix = category[:3].upper()

    max_num = 0

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                part_id = row.get("id", "")
                match = re.match(rf"^{prefix}-(\d+)$", part_id)
                if match:
                    num = int(match.group(1))
                    max_num = max(max_num, num)
    except FileNotFoundError:
        pass

    return f"{prefix}-{max_num + 1:04d}"


def main():
    parser = argparse.ArgumentParser(description="Validate CSV part files")
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).parent.parent / "src" / "schema",
        help="Path to schema directory",
    )
    parser.add_argument(
        "--next-id",
        type=Path,
        metavar="CSV",
        help="Print next available ID for the given CSV category",
    )
    parser.add_argument(
        "csv_files",
        type=Path,
        nargs="*",
        help="CSV files to validate (default: src/parts/*.csv)",
    )

    args = parser.parse_args()

    # Load schema
    try:
        schema = load_schema(args.schema)
    except Exception as e:
        print(f"Error loading schema: {e}", file=sys.stderr)
        return 1

    # Handle --next-id
    if args.next_id:
        next_id = get_next_id(args.next_id, schema)
        print(next_id)
        return 0

    # Find CSV files to validate
    if args.csv_files:
        csv_files = args.csv_files
    else:
        parts_dir = Path(__file__).parent.parent / "src" / "parts"
        csv_files = sorted(parts_dir.glob("*.csv"))

    if not csv_files:
        print("No CSV files found to validate", file=sys.stderr)
        return 1

    # Validate all files
    all_errors = []
    all_warnings = []
    all_ids = set()
    total_parts = 0

    for csv_path in csv_files:
        errors, warnings, count = validate_csv(csv_path, schema, all_ids)
        all_errors.extend(errors)
        all_warnings.extend(warnings)
        total_parts += count

        status = "FAIL" if errors else "OK"
        print(
            f"[validate] {status} {csv_path.name}: {count} parts, {len(errors)} errors"
        )

    # Print errors and warnings
    if all_warnings:
        print()
        for warning in all_warnings:
            print(f"  WARNING: {warning}")

    if all_errors:
        print()
        for error in all_errors:
            print(f"  ERROR: {error}")
        print()
        print(
            f"Validation FAILED: {len(all_errors)} errors, {len(all_warnings)} warnings"
        )
        return 1

    print()
    print(
        f"Validation OK: {total_parts} parts in {len(csv_files)} files, {len(all_warnings)} warnings"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
