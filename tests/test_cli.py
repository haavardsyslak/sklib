import re
from importlib.metadata import version
from pathlib import Path

import pytest

from sklib import __version__
from sklib.cli import main
from sklib.config import Workspace
from sklib.type_definitions import TypeRegistry


def test_package_versions_match() -> None:
    assert version("sklib") == __version__


def test_new_id_command(
    workspace: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    result = main(["--workspace", str(workspace.root), "new-id", "capacitor"])

    assert result == 0
    assert re.fullmatch(
        r"CAP-[0-9A-HJKMNP-TV-Z]{5}-[0-9A-HJKMNP-TV-Z]{5}\n",
        capsys.readouterr().out,
    )


def test_index_command_enables_progress(
    workspace: Workspace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    progress_flags: list[bool] = []

    def fake_loader(
        loaded_workspace: Workspace, *, show_progress: bool = False
    ) -> list[object]:
        assert loaded_workspace == workspace
        progress_flags.append(show_progress)
        return []

    monkeypatch.setattr("sklib.kicad.index.load_symbols", fake_loader)
    monkeypatch.setattr("sklib.kicad.index.load_footprints", fake_loader)

    result = main(["--workspace", str(workspace.root), "index"])

    assert result == 0
    assert progress_flags == [True, True]
    assert "Indexed 0 symbols and 0 footprints" in capsys.readouterr().out


def test_init_creates_portable_workspace(tmp_path: Path) -> None:
    destination = tmp_path / "library with spaces"

    result = main(["init", str(destination)])

    assert result == 0
    workspace = Workspace.load(destination)
    registry = TypeRegistry.load(workspace.types_dir)
    assert workspace.name == "Library With Spaces"
    assert 'name = "library-with-spaces"' in (destination / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert {item.name for item in registry} == {
        "capacitor",
        "connector",
        "crystal",
        "diode",
        "inductor",
        "interface",
        "led",
        "logic",
        "mechanical",
        "memory",
        "misc",
        "module",
        "mosfet",
        "processor",
        "resistor",
        "sensor",
        "switch",
        "voltage_regulator",
    }
    assert (destination / ".gitignore").is_file()
    assert (destination / "justfile").is_file()
    assert (destination / "README.md").is_file()
