import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def get_db_path() -> Path:
    return Path(__file__).parent.parent.parent / "generated" / "sklib.db"


def get_dbl_path() -> Path:
    return Path(__file__).parent.parent.parent / "kicad" / "sklib.kicad_dbl"


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return [r[1] for r in rows]


def update_component_db(component) -> None:
    """Update or insert a component in the SQLite database using INSERT OR REPLACE."""
    db_path = get_db_path()

    if not db_path.exists():
        return

    table_name = f"{component.component_type}s"
    row_data = component.to_row()

    try:
        with sqlite3.connect(db_path) as conn:
            table_cols = _get_table_columns(conn, table_name)
            if not table_cols:
                logger.warning(
                    "Table %s not found; skipping DB update for %s",
                    table_name,
                    component.id,
                )
                return

            insert_cols = [c for c in table_cols if c in row_data]
            dropped = set(row_data) - set(insert_cols)
            if dropped:
                logger.info(
                    "DB insert for %s dropping unknown columns: %s",
                    component.id,
                    sorted(dropped),
                )

            placeholders = ", ".join("?" for _ in insert_cols)
            col_names = ", ".join(f'"{c}"' for c in insert_cols)
            values = [row_data.get(c, "") for c in insert_cols]
            conn.execute(
                f'INSERT OR REPLACE INTO "{table_name}" ({col_names}) VALUES ({placeholders})',
                values,
            )
            conn.commit()
    except sqlite3.OperationalError as e:
        logger.warning("DB update failed for %s: %s", component.id, e)


def delete_from_db(component_type: str, part_id: str) -> None:
    """Delete a component from the SQLite database."""
    db_path = get_db_path()

    if not db_path.exists():
        return

    table_name = f"{component_type}s"

    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(f'DELETE FROM "{table_name}" WHERE id = ?', (part_id,))
            conn.commit()
    except sqlite3.OperationalError as e:
        logger.warning("DB delete failed for %s: %s", part_id, e)


def rebuild_table(component_type: str) -> int:
    """Rebuild a specific table from its CSV file. Returns row count."""
    from src.web.csv_store import CSVStore

    db_path = get_db_path()
    store = CSVStore()
    csv_path = store.get_csv_path(component_type)

    if not csv_path.exists():
        return 0

    table_name = f"{component_type}s"

    with open(csv_path, newline="", encoding="utf-8") as f:
        import csv

        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            return 0

        columns = list(reader.fieldnames)

        with sqlite3.connect(db_path) as conn:
            conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')

            col_defs = ", ".join(f'"{col}" TEXT' for col in columns)
            conn.execute(f'CREATE TABLE "{table_name}" ({col_defs})')

            conn.execute(
                f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_id" ON "{table_name}" ("id")'
            )
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_mpn" ON "{table_name}" ("mpn")'
            )

            placeholders = ", ".join("?" for _ in columns)
            col_names = ", ".join(f'"{col}"' for col in columns)
            insert_sql = (
                f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders})'
            )

            row_count = 0
            for row in reader:
                values = [row.get(col, "") for col in columns]
                conn.execute(insert_sql, values)
                row_count += 1

            conn.commit()

    return row_count
