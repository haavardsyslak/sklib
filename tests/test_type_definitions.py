from pathlib import Path

import pytest

from sklib.type_definitions import TypeDefinitionError, TypeRegistry


def test_workspace_templates_match_example_definitions() -> None:
    root = Path(__file__).resolve().parents[1]
    examples = root / "types"
    templates = root / "src" / "sklib" / "templates" / "workspace" / "types"

    assert {
        path.name: path.read_text(encoding="utf-8") for path in examples.glob("*.toml")
    } == {
        path.name: path.read_text(encoding="utf-8") for path in templates.glob("*.toml")
    }


def test_synthetic_type_requires_no_python_changes(tmp_path: Path) -> None:
    definition = """\
schema_version = 1
name = "test_component"
label = "Test component"
plural = "Test components"
prefix = "TST"
value_field = "test_value"

[[fields]]
name = "test_value"
label = "Test value"
kind = "integer"
required = true

[[fields]]
name = "mode"
label = "Mode"
kind = "enum"
options = ["one", "two"]
"""
    (tmp_path / "test_component.toml").write_text(definition, encoding="utf-8")

    registry = TypeRegistry.load(tmp_path)
    component_type = registry.require("test_component")

    assert component_type.prefix == "TST"
    assert component_type.validate_specs({"test_value": 4, "mode": "two"}) == []
    assert component_type.validate_specs({"test_value": "4"}) == [
        "specs.test_value: must be an integer"
    ]


def test_mpn_can_supply_kicad_value(tmp_path: Path) -> None:
    definition = """\
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
"""
    (tmp_path / "led.toml").write_text(definition, encoding="utf-8")

    component_type = TypeRegistry.load(tmp_path).require("led")

    assert component_type.value_field == "mpn"
    assert component_type.validate_specs({"color": "Red"}) == []


def test_specification_cannot_override_core_database_columns(
    tmp_path: Path,
) -> None:
    definition = """\
schema_version = 1
name = "bad"
label = "Bad"
plural = "Bad"
prefix = "BAD"
value_field = "value"

[[fields]]
name = "value"
label = "Value"
kind = "string"
required = true
"""
    (tmp_path / "bad.toml").write_text(definition, encoding="utf-8")

    with pytest.raises(TypeDefinitionError, match="reserved fields: value"):
        TypeRegistry.load(tmp_path)
