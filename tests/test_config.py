from pathlib import Path

import pytest

from sklib.config import ConfigurationError, Workspace


def test_unknown_workspace_setting_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "sklib.toml").write_text(
        """\
[library]
name = "Test"

[paths]
partz = "parts"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="unknown paths keys: partz"):
        Workspace.load(tmp_path)


def test_windows_gets_conventional_odbc_driver_name(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SKLIB_ODBC_DRIVER", raising=False)
    monkeypatch.setattr("sklib.config.platform.system", lambda: "Windows")

    assert workspace.odbc_driver() == "SQLite3 ODBC Driver"


def test_workspace_env_can_configure_odbc_driver(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SKLIB_ODBC_DRIVER", raising=False)
    (workspace.root / ".env").write_text(
        "SKLIB_ODBC_DRIVER=Workspace Driver\n", encoding="utf-8"
    )

    loaded = Workspace.load(workspace.root)

    assert loaded.odbc_driver() == "Workspace Driver"


def test_odbc_driver_can_be_overridden(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKLIB_ODBC_DRIVER", "Local Driver")

    assert workspace.odbc_driver() == "Local Driver"
