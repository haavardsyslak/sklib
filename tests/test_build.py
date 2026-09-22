import json
import sqlite3
from pathlib import Path

from sklib.build import build_catalog
from sklib.config import Workspace
from sklib.models import KicadMapping, Part
from sklib.store import Catalog


def test_builds_logically_stable_database(workspace: Workspace) -> None:
    part = Part(
        schema_version=1,
        id="CAP-0001",
        component_type="capacitor",
        mpn="TEST-100",
        manufacturer="Example",
        description="Test capacitor",
        keywords=["capacitor", "x7r"],
        kicad=KicadMapping(
            symbol="Device:C",
            footprint="Capacitor_SMD:C_0402_1005Metric",
        ),
        specs={"capacitance": "100nF", "package": "0402"},
    )
    Catalog(workspace).save(part)

    first = build_catalog(workspace)
    first_rows = _database_rows(first.database_path)
    second = build_catalog(workspace)
    second_rows = _database_rows(second.database_path)

    assert first.part_count == 1
    assert first.table_count == 1
    assert first_rows == second_rows
    assert first_rows == [("CAP-0001", "TEST-100", "100nF", "100nF", "0402")]
    with sqlite3.connect(second.database_path) as connection:
        search_terms = connection.execute(
            "SELECT search_terms FROM capacitors WHERE id = 'CAP-0001'"
        ).fetchone()
    assert search_terms == ("CAP-0001 TEST-100 TEST100 Example capacitor x7r",)

    config = json.loads(second.dbl_path.read_text(encoding="utf-8"))
    library = config["libraries"][0]
    assert library["table"] == "capacitors"
    assert library["properties"]["keywords"] == "search_terms"
    assert [field["column"] for field in library["fields"]].count("package") == 1
    assert "tolerance" in [field["column"] for field in library["fields"]]
    assert str(workspace.database_path) in config["source"]["connection_string"]


def test_build_uses_mpn_as_value_when_declared(workspace: Workspace) -> None:
    (workspace.types_dir / "capacitor.toml").unlink()
    (workspace.types_dir / "led.toml").write_text(
        """\
schema_version = 1
name = "led"
label = "LED"
plural = "LEDs"
prefix = "LED"
value_field = "mpn"

[[fields]]
name = "color"
label = "Color"
kind = "string"
required = true
""",
        encoding="utf-8",
    )
    part = Part(
        schema_version=1,
        id="LED-0001",
        component_type="led",
        mpn="TEST-LED-100",
        manufacturer="Example",
        description="Test LED",
        kicad=KicadMapping(
            symbol="Device:LED",
            footprint="LED_SMD:LED_0603_1608Metric",
        ),
        specs={"color": "Red"},
    )
    Catalog(workspace).save(part)

    result = build_catalog(workspace)

    with sqlite3.connect(result.database_path) as connection:
        assert connection.execute(
            "SELECT value FROM leds WHERE id = 'LED-0001'"
        ).fetchone() == ("TEST-LED-100",)


def test_rebuild_updates_existing_database_connection(workspace: Workspace) -> None:
    part = Part(
        schema_version=1,
        id="CAP-0001",
        component_type="capacitor",
        mpn="TEST-100",
        manufacturer="Example",
        description="Test capacitor",
        kicad=KicadMapping(
            symbol="Device:C_Small",
            footprint="Capacitor_SMD:C_0402_1005Metric",
        ),
        specs={"capacitance": "100nF", "package": "0402"},
    )
    catalog = Catalog(workspace)
    catalog.save(part)
    build_catalog(workspace)

    with sqlite3.connect(workspace.database_path) as existing_connection:
        assert existing_connection.execute(
            "SELECT value FROM capacitors WHERE id = 'CAP-0001'"
        ).fetchone() == ("100nF",)
        initial_data_version = existing_connection.execute(
            "PRAGMA data_version"
        ).fetchone()[0]
        updated = part.model_copy(
            update={
                "specs": {"capacitance": "220nF", "package": "0402"},
                "kicad": KicadMapping(
                    symbol="Device:C",
                    footprint="Capacitor_SMD:C_0402_1005Metric",
                ),
            }
        )
        catalog.save(updated, original_id=part.id)
        build_catalog(workspace)

        assert existing_connection.execute(
            "SELECT value, symbol FROM capacitors WHERE id = 'CAP-0001'"
        ).fetchone() == ("220nF", "Device:C")
        updated_data_version = existing_connection.execute(
            "PRAGMA data_version"
        ).fetchone()[0]
        assert updated_data_version > initial_data_version


def _database_rows(path: Path) -> list[tuple[str, ...]]:
    with sqlite3.connect(path) as connection:
        primary_key = connection.execute(
            'SELECT pk FROM pragma_table_info("capacitors") WHERE name = "id"'
        ).fetchone()
        assert primary_key == (1,)
        return connection.execute(
            "SELECT id, mpn, value, capacitance, package FROM capacitors"
        ).fetchall()
