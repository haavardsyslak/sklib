import re
import secrets
import sqlite3
import threading
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import ValidationError

from sklib import __version__
from sklib.build import BuildError, build_catalog
from sklib.config import Workspace
from sklib.kicad.index import LibraryEntry, load_footprints, load_symbols
from sklib.models import Part
from sklib.store import Catalog, CatalogError
from sklib.type_definitions import ComponentTypeDefinition, FieldDefinition


def create_app(workspace: Workspace) -> FastAPI:
    """Create a web editor bound to one library workspace."""
    app = FastAPI(
        title=f"{workspace.name} — SKLib",
        description="Local editor for a Git-backed KiCad component library",
        version=__version__,
    )
    app.state.workspace = workspace
    app.state.catalog = Catalog(workspace)
    app.state.csrf_token = secrets.token_urlsafe(32)
    app.state.symbol_index = None
    app.state.footprint_index = None
    app.state.symbol_index_lock = threading.Lock()
    app.state.footprint_index_lock = threading.Lock()

    package_dir = Path(__file__).parent
    static_dir = package_dir / "static"
    app.state.asset_version = max(
        path.stat().st_mtime_ns for path in static_dir.iterdir() if path.is_file()
    )
    templates = Environment(
        loader=FileSystemLoader(str(package_dir / "templates")),
        autoescape=select_autoescape(["html"]),
    )
    app.state.templates = templates
    app.mount(
        "/static",
        StaticFiles(directory=str(static_dir)),
        name="static",
    )

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/components")

    @app.get("/components", response_class=HTMLResponse)
    def list_parts(
        request: Request,
        component_type: str | None = None,
        q: str = "",
        saved: str = "",
        build_seconds: str = "",
    ) -> HTMLResponse:
        catalog = _catalog(request)
        parts, issues = catalog.scan()
        component_counts = Counter(part.component_type for part in parts)
        total_count = len(parts)
        if component_type:
            parts = [part for part in parts if part.component_type == component_type]
        if q.strip():
            query = q.strip().casefold()
            parts = [part for part in parts if _matches(part, query)]
        return _render(
            request,
            "list.html",
            parts=parts,
            issues=issues,
            selected_type=component_type,
            query=q,
            saved=saved,
            build_seconds=build_seconds,
            component_counts=component_counts,
            total_count=total_count,
        )

    @app.get("/components/new", response_class=HTMLResponse)
    def new_part(request: Request, component_type: str) -> HTMLResponse:
        catalog = _catalog(request)
        definition = catalog.types.get(component_type)
        if definition is None:
            return _not_found(request, component_type)
        values = _blank_values(catalog.new_id(component_type), definition)
        return _render_form(request, definition, values, [], False)

    @app.post("/components", response_class=HTMLResponse)
    async def create_part(request: Request) -> HTMLResponse:
        form = dict(await request.form())
        _require_csrf(request, form)
        return _save_form(request, form, None)

    @app.get("/components/{component_type}/{part_id}", response_class=HTMLResponse)
    def part_detail(
        request: Request, component_type: str, part_id: str
    ) -> HTMLResponse:
        catalog = _catalog(request)
        part = catalog.get(component_type, part_id)
        if part is None:
            return _not_found(request, part_id)
        return _render(
            request,
            "detail.html",
            part=part,
            definition=catalog.types.require(component_type),
            selected_type=component_type,
        )

    @app.get(
        "/components/{component_type}/{part_id}/edit",
        response_class=HTMLResponse,
    )
    def edit_part(request: Request, component_type: str, part_id: str) -> HTMLResponse:
        catalog = _catalog(request)
        part = catalog.get(component_type, part_id)
        if part is None:
            return _not_found(request, part_id)
        definition = catalog.types.require(component_type)
        return _render_form(request, definition, _part_values(part), [], True)

    @app.post(
        "/components/{component_type}/{part_id}",
        response_class=HTMLResponse,
    )
    async def update_part(
        request: Request, component_type: str, part_id: str
    ) -> HTMLResponse:
        form = dict(await request.form())
        _require_csrf(request, form)
        form["component_type"] = component_type
        return _save_form(request, form, part_id)

    @app.post("/components/{component_type}/{part_id}/delete")
    async def delete_part(
        request: Request, component_type: str, part_id: str
    ) -> RedirectResponse:
        form = dict(await request.form())
        _require_csrf(request, form)
        catalog = _catalog(request)
        if catalog.delete(component_type, part_id):
            build_catalog(_workspace(request))
        return RedirectResponse(
            f"/components?component_type={component_type}", status_code=303
        )

    @app.get("/api/kicad/symbols")
    def symbols(request: Request, q: str = "", library: str = "") -> JSONResponse:
        entries = _cached_index(request, "symbol")
        return JSONResponse(_search_index(entries, q, library))

    @app.get("/api/kicad/footprints")
    def footprints(request: Request, q: str = "", library: str = "") -> JSONResponse:
        entries = _cached_index(request, "footprint")
        return JSONResponse(_search_index(entries, q, library))

    @app.get("/api/suppliers/digikey/search")
    def search_digikey(request: Request, q: str) -> JSONResponse:
        from requests import RequestException

        from sklib.suppliers.digikey import (
            DigikeyClient,
            SupplierConfigurationError,
        )

        _require_csrf_header(request)
        if not q.strip():
            return JSONResponse({"error": "Search query is required"}, status_code=400)
        try:
            products = DigikeyClient(_workspace(request).root).search(q.strip())
        except SupplierConfigurationError as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        except (RequestException, RuntimeError, ValueError) as error:
            return JSONResponse(
                {"error": f"DigiKey request failed: {error}"}, status_code=502
            )
        return JSONResponse({"results": [item.to_dict() for item in products]})

    return app


def _cached_index(request: Request, kind: str) -> list[LibraryEntry]:
    attribute = f"{kind}_index"
    workspace = _workspace(request)
    signature = _repo_index_signature(workspace.kicad_dir, kind)
    cached = getattr(request.app.state, attribute)
    if cached is not None and cached[0] == signature:
        return cached[1]

    lock = getattr(request.app.state, f"{kind}_index_lock")
    with lock:
        cached = getattr(request.app.state, attribute)
        if cached is None or cached[0] != signature:
            loader = load_symbols if kind == "symbol" else load_footprints
            cached = (signature, loader(workspace))
            setattr(request.app.state, attribute, cached)
    return cached[1]


def _repo_index_signature(
    directory: Path, kind: str
) -> tuple[tuple[str, int, int], ...]:
    if not directory.is_dir():
        return ()
    pattern = "*.kicad_sym" if kind == "symbol" else "*.kicad_mod"
    signature: list[tuple[str, int, int]] = []
    for path in sorted(directory.rglob(pattern)):
        try:
            stat = path.stat()
        except OSError:
            continue
        signature.append(
            (str(path.relative_to(directory)), stat.st_mtime_ns, stat.st_size)
        )
    return tuple(signature)


def _search_index(
    entries: list[LibraryEntry], query: str, library: str
) -> dict[str, object]:
    normalized_query = query.strip().casefold()[:200]
    normalized_library = library.strip().casefold()[:200]
    scoped = (
        [entry for entry in entries if entry.library.casefold() == normalized_library]
        if normalized_library
        else entries
    )

    library_results: list[dict[str, object]] = []
    if normalized_query and not normalized_library:
        counts = Counter(entry.library for entry in entries)
        matching_libraries = [
            name for name in counts if normalized_query in name.casefold()
        ]
        matching_libraries.sort(
            key=lambda name: (_library_score(name, normalized_query), name.casefold())
        )
        library_results = [
            {"name": name, "count": counts[name]} for name in matching_libraries[:12]
        ]

    if normalized_query:
        matches = [
            entry for entry in scoped if normalized_query in entry.full_name.casefold()
        ]
        matches.sort(
            key=lambda entry: (
                _entry_score(entry, normalized_query),
                entry.full_name.casefold(),
            )
        )
    elif normalized_library:
        matches = list(scoped)
    else:
        matches = []

    return {
        "libraries": library_results,
        "items": [asdict(entry) for entry in matches[:50]],
        "total": len(matches),
    }


def _library_score(name: str, query: str) -> int:
    normalized = name.casefold()
    if normalized == query:
        return 0
    if normalized.startswith(query):
        return 1
    return 2


def _entry_score(entry: LibraryEntry, query: str) -> int:
    name = entry.name.casefold()
    library = entry.library.casefold()
    full_name = entry.full_name.casefold()
    if name == query:
        return 0
    if full_name == query:
        return 1
    if name.startswith(query):
        return 2
    if library == query:
        return 3
    if library.startswith(query):
        return 4
    if query in name:
        return 5
    return 6


def _save_form(
    request: Request, form: dict[str, Any], original_id: str | None
) -> HTMLResponse:
    catalog = _catalog(request)
    component_type = str(form.get("component_type", ""))
    definition = catalog.types.get(component_type)
    if definition is None:
        return _not_found(request, component_type)

    existing = catalog.get(component_type, original_id) if original_id else None
    values = _clean_form_values(form)
    try:
        part = _part_from_form(values, definition, existing)
        path = catalog.save(part, original_id=original_id)
    except ValidationError as error:
        errors = _validation_messages(error)
        return _render_form(
            request, definition, values, errors, original_id is not None
        )
    except CatalogError as error:
        errors = [issue.message for issue in error.issues]
        return _render_form(
            request, definition, values, errors, original_id is not None
        )
    except (OSError, ValueError) as error:
        return _render_form(
            request,
            definition,
            values,
            [f"Failed to save component: {error}"],
            original_id is not None,
        )

    try:
        result = build_catalog(_workspace(request))
    except (BuildError, CatalogError, OSError, sqlite3.Error) as error:
        return _render_form(
            request,
            definition,
            values,
            [f"Saved {path.name}, but DBLib rebuild failed: {error}"],
            original_id is not None,
        )

    return RedirectResponse(
        "/components?"
        f"component_type={part.component_type}&saved={path.stem}&"
        f"build_seconds={result.elapsed_seconds:.3f}",
        status_code=303,
    )


def _part_from_form(
    values: dict[str, str],
    definition: ComponentTypeDefinition,
    existing: Part | None,
) -> Part:
    specs: dict[str, object] = {}
    for field in definition.fields:
        raw = values.get(f"spec__{field.name}", "").strip()
        if not raw:
            continue
        specs[field.name] = _convert_field(field, raw)

    suppliers: list[dict[str, str]] = []
    supplier_values = {
        "name": values.get("supplier_name", "").strip(),
        "sku": values.get("supplier_sku", "").strip(),
        "product_url": values.get("supplier_url", "").strip(),
    }
    if any(supplier_values.values()):
        suppliers.append(supplier_values)
    if existing and len(existing.suppliers) > 1:
        suppliers.extend(supplier.model_dump() for supplier in existing.suppliers[1:])

    payload = {
        "schema_version": 1,
        "id": values.get("id", ""),
        "component_type": definition.name,
        "mpn": values.get("mpn", ""),
        "manufacturer": values.get("manufacturer", ""),
        "description": values.get("description", ""),
        "manufacturer_status": values.get("manufacturer_status", "active"),
        "datasheet": values.get("datasheet", ""),
        "keywords": _keywords(values.get("keywords", "")),
        "notes": values.get("notes", ""),
        "kicad": {
            "symbol": values.get("symbol", ""),
            "footprint": values.get("footprint", ""),
            "exclude_from_bom": values.get("exclude_from_bom") == "on",
        },
        "specs": specs,
        "suppliers": suppliers,
    }
    return Part.model_validate(payload)


def _convert_field(field: FieldDefinition, raw: str) -> object:
    if field.kind == "integer":
        try:
            return int(raw)
        except ValueError:
            return raw
    if field.kind == "number":
        try:
            return float(raw)
        except ValueError:
            return raw
    if field.kind == "boolean":
        return raw.casefold() in {"1", "true", "yes", "on"}
    return raw


def _part_values(part: Part) -> dict[str, str]:
    supplier = part.suppliers[0] if part.suppliers else None
    values = {
        "id": part.id,
        "component_type": part.component_type,
        "mpn": part.mpn,
        "manufacturer": part.manufacturer,
        "description": part.description,
        "manufacturer_status": part.manufacturer_status,
        "datasheet": part.datasheet,
        "keywords": ", ".join(part.keywords),
        "notes": part.notes,
        "symbol": part.kicad.symbol,
        "footprint": part.kicad.footprint,
        "exclude_from_bom": "on" if part.kicad.exclude_from_bom else "",
        "supplier_name": supplier.name if supplier else "",
        "supplier_sku": supplier.sku if supplier else "",
        "supplier_url": supplier.product_url if supplier else "",
    }
    values.update({f"spec__{key}": str(value) for key, value in part.specs.items()})
    return values


def _blank_values(part_id: str, definition: ComponentTypeDefinition) -> dict[str, str]:
    return {
        "id": part_id,
        "component_type": definition.name,
        "manufacturer_status": "active",
        "symbol": definition.default_symbol,
    }


def _clean_form_values(form: dict[str, Any]) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in form.items()
        if isinstance(value, (str, int, float))
    }


def _keywords(value: str) -> list[str]:
    return [item for item in re.split(r"[\s,]+", value.strip()) if item]


def _validation_messages(error: ValidationError) -> list[str]:
    result = []
    for item in error.errors(include_url=False):
        location = ".".join(str(value) for value in item["loc"])
        result.append(f"{location}: {item['msg']}")
    return result


def _matches(part: Part, query: str) -> bool:
    values = [
        part.id,
        part.mpn,
        part.manufacturer,
        part.description,
        *part.keywords,
        *(str(value) for value in part.specs.values()),
    ]
    return any(query in value.casefold() for value in values)


def _render_form(
    request: Request,
    definition: ComponentTypeDefinition,
    values: dict[str, str],
    errors: list[str],
    editing: bool,
) -> HTMLResponse:
    return _render(
        request,
        "form.html",
        definition=definition,
        values=values,
        errors=errors,
        editing=editing,
        selected_type=definition.name,
    )


def _render(
    request: Request,
    template_name: str,
    status_code: int = 200,
    **context: Any,
) -> HTMLResponse:
    template = request.app.state.templates.get_template(template_name)
    if "component_counts" not in context:
        parts, _ = _catalog(request).scan()
        context["component_counts"] = Counter(part.component_type for part in parts)
        context["total_count"] = len(parts)
    context.setdefault("query", "")
    context.setdefault("selected_type", None)
    return HTMLResponse(
        template.render(
            request=request,
            workspace=_workspace(request),
            component_types=list(_catalog(request).types),
            csrf_token=request.app.state.csrf_token,
            asset_version=request.app.state.asset_version,
            **context,
        ),
        status_code=status_code,
    )


def _not_found(request: Request, value: str) -> HTMLResponse:
    return _render(request, "not_found.html", status_code=404, value=value)


def _require_csrf(request: Request, form: dict[str, Any]) -> None:
    submitted = form.get("csrf_token")
    expected = request.app.state.csrf_token
    if not isinstance(submitted, str) or not secrets.compare_digest(
        submitted, expected
    ):
        raise HTTPException(status_code=403, detail="Invalid form token")


def _require_csrf_header(request: Request) -> None:
    submitted = request.headers.get("X-CSRF-Token", "")
    expected = request.app.state.csrf_token
    if not secrets.compare_digest(submitted, expected):
        raise HTTPException(status_code=403, detail="Invalid request token")


def _workspace(request: Request) -> Workspace:
    return request.app.state.workspace


def _catalog(request: Request) -> Catalog:
    return request.app.state.catalog
