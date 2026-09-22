import re

import pytest

from sklib.config import Workspace
from sklib.models import KicadMapping, Part
from sklib.store import Catalog, CatalogError


def capacitor(part_id: str = "CAP-0001", mpn: str = "TEST-100") -> Part:
    return Part(
        schema_version=1,
        id=part_id,
        component_type="capacitor",
        mpn=mpn,
        manufacturer="Example",
        description="Test capacitor",
        keywords=["capacitor", "Capacitor", "x7r"],
        kicad=KicadMapping(
            symbol="Device:C",
            footprint="Capacitor_SMD:C_0402_1005Metric",
        ),
        specs={"capacitance": "100nF", "package": "0402"},
    )


def test_save_load_and_legacy_id(workspace: Workspace) -> None:
    catalog = Catalog(workspace)

    path = catalog.save(capacitor())
    loaded = catalog.get("capacitor", "CAP-0001")

    assert path == workspace.parts_dir / "capacitor" / "CAP-0001.toml"
    assert loaded is not None
    assert loaded.specs["capacitance"] == "100nF"
    assert loaded.keywords == ["capacitor", "x7r"]


def test_new_id_uses_random_crockford_base32(workspace: Workspace) -> None:
    part_id = Catalog(workspace).new_id("capacitor")

    assert re.fullmatch(r"CAP-[0-9A-HJKMNP-TV-Z]{5}-[0-9A-HJKMNP-TV-Z]{5}", part_id)


def test_new_id_skips_existing_path(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = workspace.parts_dir / "capacitor"
    directory.mkdir()
    (directory / "CAP-7K3MP-9QWX2.toml").touch()
    suffixes = iter(["7K3MP9QWX2", "4F8NR6VCW3"])
    monkeypatch.setattr("sklib.store._random_id_suffix", lambda: next(suffixes))

    assert Catalog(workspace).new_id("capacitor") == "CAP-4F8NR-6VCW3"


def test_random_id_can_be_saved(workspace: Workspace) -> None:
    catalog = Catalog(workspace)
    part = capacitor(part_id="CAP-7K3MP-9QWX2")

    path = catalog.save(part)

    assert path.name == "CAP-7K3MP-9QWX2.toml"
    assert catalog.get("capacitor", part.id) == part


def test_save_preserves_existing_comments(workspace: Workspace) -> None:
    catalog = Catalog(workspace)
    path = catalog.save(capacitor())
    content = path.read_text(encoding="utf-8")
    path.write_text(f"# reviewed by human\n{content}", encoding="utf-8")
    changed = capacitor().model_copy(update={"description": "Changed description"})

    catalog.save(changed, original_id=changed.id)

    result = path.read_text(encoding="utf-8")
    assert result.startswith("# reviewed by human\n")
    assert 'description = "Changed description"' in result


def test_duplicate_manufacturer_and_mpn_is_rejected(workspace: Workspace) -> None:
    catalog = Catalog(workspace)
    catalog.save(capacitor())
    duplicate = capacitor(part_id="CAP-0002", mpn="test-100")

    with pytest.raises(CatalogError, match="duplicate manufacturer and MPN"):
        catalog.save(duplicate)


def test_existing_id_cannot_be_overwritten_as_new(workspace: Workspace) -> None:
    catalog = Catalog(workspace)
    catalog.save(capacitor())
    replacement = capacitor(mpn="OTHER-100").model_copy(
        update={"description": "Replacement"}
    )

    with pytest.raises(CatalogError, match="duplicate ID"):
        catalog.save(replacement)


def test_unknown_spec_is_reported(workspace: Workspace) -> None:
    catalog = Catalog(workspace)
    invalid = capacitor().model_copy(
        update={
            "specs": {
                "capacitance": "100nF",
                "package": "0402",
                "capacitence": "typo",
            }
        }
    )

    with pytest.raises(CatalogError, match="specs.capacitence: unknown field"):
        catalog.save(invalid)


def test_schema_version_is_required(workspace: Workspace) -> None:
    path = workspace.parts_dir / "capacitor" / "CAP-0001.toml"
    path.parent.mkdir()
    path.write_text(
        """\
id = "CAP-0001"
component_type = "capacitor"
mpn = "TEST-100"
manufacturer = "Example"
description = "Test"

[kicad]
symbol = "Device:C"
footprint = "Capacitor_SMD:C_0402_1005Metric"

[specs]
capacitance = "100nF"
package = "0402"
""",
        encoding="utf-8",
    )

    _, issues = Catalog(workspace).scan()

    assert any("schema_version: Field required" in str(issue) for issue in issues)


def test_path_must_match_type_and_id(workspace: Workspace) -> None:
    wrong = workspace.parts_dir / "wrong" / "other.toml"
    wrong.parent.mkdir()
    wrong.write_text(
        """\
schema_version = 1
id = "CAP-0001"
component_type = "capacitor"
mpn = "TEST-100"
manufacturer = "Example"
description = "Test"

[kicad]
symbol = "Device:C"
footprint = "Capacitor_SMD:C_0402_1005Metric"

[specs]
capacitance = "100nF"
package = "0402"
""",
        encoding="utf-8",
    )

    _, issues = Catalog(workspace).scan()

    assert len(issues) == 1
    assert "record must be stored at parts/capacitor/CAP-0001.toml" in str(issues[0])
