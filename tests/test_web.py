import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

from sklib.config import Workspace
from sklib.kicad.paths import KiCadPaths
from sklib.web.app import create_app


def component_form(client: TestClient) -> dict[str, str]:
    return {
        "csrf_token": client.app.state.csrf_token,
        "component_type": "capacitor",
        "id": "CAP-0001",
        "mpn": "TEST-100",
        "manufacturer": "Example",
        "description": "Test capacitor",
        "manufacturer_status": "active",
        "symbol": "Device:C",
        "footprint": "Capacitor_SMD:C_0402_1005Metric",
        "spec__capacitance": "100nF",
        "spec__package": "0402",
    }


def test_form_is_derived_from_type_definition(workspace: Workspace) -> None:
    client = TestClient(create_app(workspace))

    response = client.get("/components/new?component_type=capacitor")

    assert response.status_code == 200
    assert 'name="spec__capacitance"' in response.text
    assert 'name="spec__package"' in response.text
    assert 'id="symbol-library"' in response.text
    assert 'id="footprint-library"' in response.text
    assert re.search(
        r'name="id" value="CAP-[0-9A-HJKMNP-TV-Z]{5}-'
        r'[0-9A-HJKMNP-TV-Z]{5}" required readonly',
        response.text,
    )


def test_new_declarative_field_reaches_form_and_database(
    workspace: Workspace,
) -> None:
    definition_path = workspace.types_dir / "capacitor.toml"
    with open(definition_path, "a", encoding="utf-8") as file:
        file.write(
            """\

[[fields]]
name = "test_rating"
label = "Test rating"
kind = "string"
"""
        )
    client = TestClient(create_app(workspace))

    form = client.get("/components/new?component_type=capacitor")
    data = component_form(client)
    data["spec__test_rating"] = "special"
    response = client.post("/components", data=data, follow_redirects=False)

    assert 'name="spec__test_rating"' in form.text
    assert response.status_code == 303
    with sqlite3.connect(workspace.database_path) as connection:
        assert connection.execute("SELECT test_rating FROM capacitors").fetchone() == (
            "special",
        )


def test_navigation_shows_component_counts_and_active_type(
    workspace: Workspace,
) -> None:
    client = TestClient(create_app(workspace))
    create = client.post(
        "/components", data=component_form(client), follow_redirects=False
    )
    assert create.status_code == 303

    response = client.get("/components?component_type=capacitor")

    assert "<strong>1</strong> components" in response.text
    assert re.search(
        r'class="sidebar-link active"\s+'
        r'href="/components\?component_type=capacitor"\s+aria-current="page"',
        response.text,
    )
    assert "TEST-100" in response.text
    assert "Add capacitor" in response.text


def test_create_component_writes_toml_and_rebuilds_database(
    workspace: Workspace,
) -> None:
    client = TestClient(create_app(workspace))

    response = client.post(
        "/components", data=component_form(client), follow_redirects=False
    )

    assert response.status_code == 303
    path = workspace.parts_dir / "capacitor" / "CAP-0001.toml"
    assert path.is_file()
    assert workspace.database_path.is_file()
    assert workspace.dbl_path.is_file()
    with sqlite3.connect(workspace.database_path) as connection:
        assert connection.execute("SELECT mpn, value FROM capacitors").fetchone() == (
            "TEST-100",
            "100nF",
        )


def test_edit_and_delete_rebuild_database(workspace: Workspace) -> None:
    app = create_app(workspace)
    client = TestClient(app)
    create = client.post(
        "/components", data=component_form(client), follow_redirects=False
    )
    assert create.status_code == 303

    changed = component_form(client)
    changed["description"] = "Updated capacitor"
    update = client.post(
        "/components/capacitor/CAP-0001",
        data=changed,
        follow_redirects=False,
    )

    assert update.status_code == 303
    detail = client.get("/components/capacitor/CAP-0001")
    assert "Updated capacitor" in detail.text
    with sqlite3.connect(workspace.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM capacitors").fetchone() == (1,)

    delete = client.post(
        "/components/capacitor/CAP-0001/delete",
        data={"csrf_token": app.state.csrf_token},
        follow_redirects=False,
    )

    assert delete.status_code == 303
    assert not list(workspace.parts_dir.rglob("*.toml"))
    with sqlite3.connect(workspace.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM capacitors").fetchone() == (0,)


def test_validation_keeps_submitted_values(workspace: Workspace) -> None:
    client = TestClient(create_app(workspace))

    data = component_form(client)
    data["symbol"] = "invalid"
    response = client.post("/components", data=data)

    assert response.status_code == 200
    assert "must use Library:Name format" in response.text
    assert 'value="TEST-100"' in response.text
    assert not list(workspace.parts_dir.rglob("*.toml"))


def test_cross_site_form_submission_is_rejected(workspace: Workspace) -> None:
    client = TestClient(create_app(workspace))
    data = component_form(client)
    del data["csrf_token"]

    response = client.post("/components", data=data)

    assert response.status_code == 403
    assert not list(workspace.parts_dir.rglob("*.toml"))


def test_cross_site_supplier_request_is_rejected(workspace: Workspace) -> None:
    client = TestClient(create_app(workspace))

    response = client.get("/api/suppliers/digikey/search?q=TEST-100")

    assert response.status_code == 403


def test_missing_digikey_credentials_are_actionable(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DIGIKEY_CLIENT_ID", raising=False)
    monkeypatch.delenv("DIGIKEY_CLIENT_SECRET", raising=False)
    client = TestClient(create_app(workspace))

    response = client.get(
        "/api/suppliers/digikey/search?q=TEST-100",
        headers={"X-CSRF-Token": client.app.state.csrf_token},
    )

    assert response.status_code == 400
    assert "DIGIKEY_CLIENT_ID" in response.json()["error"]


def test_symbol_search_returns_libraries_and_scoped_items(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sklib.kicad.index.detect_system_paths",
        lambda: KiCadPaths(symbols=None, footprints=None),
    )
    (workspace.kicad_dir / "Device.kicad_sym").write_text(
        '(kicad_symbol_lib (symbol "C_small" (property "Reference" "C")))',
        encoding="utf-8",
    )
    client = TestClient(create_app(workspace))

    global_search = client.get("/api/kicad/symbols?q=device")
    scoped_search = client.get("/api/kicad/symbols?library=Device&q=small")

    assert global_search.json()["libraries"] == [{"name": "Device", "count": 1}]
    assert global_search.json()["items"][0]["name"] == "C_small"
    assert scoped_search.json()["libraries"] == []
    assert scoped_search.json()["items"][0]["library"] == "Device"

    (workspace.kicad_dir / "Local.kicad_sym").write_text(
        '(kicad_symbol_lib (symbol "New_part"))', encoding="utf-8"
    )
    refreshed = client.get("/api/kicad/symbols?q=New_part")
    assert refreshed.json()["items"][0]["library"] == "Local"


def test_repo_footprints_are_searchable(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sklib.kicad.index.detect_system_paths",
        lambda: KiCadPaths(symbols=None, footprints=None),
    )
    library = workspace.kicad_dir / "Example.pretty"
    library.mkdir()
    (library / "Example_0402.kicad_mod").write_text(
        '(footprint "Example_0402" (descr "Test footprint"))',
        encoding="utf-8",
    )
    client = TestClient(create_app(workspace))

    response = client.get("/api/kicad/footprints?q=Example")

    assert response.status_code == 200
    assert response.json() == {
        "libraries": [{"name": "Example", "count": 1}],
        "items": [
            {
                "library": "Example",
                "name": "Example_0402",
                "source": "repo",
                "properties": {"Description": "Test footprint"},
            }
        ],
        "total": 1,
    }

    scoped = client.get("/api/kicad/footprints?library=Example&q=0402")
    assert scoped.json()["libraries"] == []
    assert scoped.json()["items"][0]["name"] == "Example_0402"
