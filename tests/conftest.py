from pathlib import Path

import pytest

from sklib.config import Workspace

TYPE_DEFINITION = """\
schema_version = 1
name = "capacitor"
label = "Capacitor"
plural = "Capacitors"
prefix = "CAP"
value_field = "capacitance"
default_symbol = "Device:C"

[[fields]]
name = "capacitance"
label = "Capacitance"
kind = "string"
required = true

[[fields]]
name = "package"
label = "Package"
kind = "string"
required = true

[[fields]]
name = "tolerance"
label = "Tolerance"
kind = "string"
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    (tmp_path / "sklib.toml").write_text(
        """\
[library]
name = "Test Parts"
description = "Test catalog"

[paths]
parts = "parts"
types = "types"
kicad = "kicad"
generated = "generated"
""",
        encoding="utf-8",
    )
    (tmp_path / "types").mkdir()
    (tmp_path / "types" / "capacitor.toml").write_text(
        TYPE_DEFINITION, encoding="utf-8"
    )
    (tmp_path / "parts").mkdir()
    (tmp_path / "kicad").mkdir()
    return Workspace.load(tmp_path)
