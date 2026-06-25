from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.web.csv_store import CSVStore, Component
from src.web.db_update import update_component_db, delete_from_db
from src.web.schema import (
    get_component_types,
    get_id_prefix,
    get_common_symbol,
    get_columns,
)

router = APIRouter()

_BASE_FIELDS = {
    "component_type", "id", "mpn", "manufacturer", "description",
    "symbol", "footprint", "lifecycle_status", "value", "tolerance",
    "package", "rated_voltage", "operating_temp", "datasheet",
    "supplier", "supplier_sku", "notes", "keywords", "exclude_from_bom",
}


def _component_from_form(form: dict, component_type: str) -> Component:
    extra = {k: v for k, v in form.items() if k not in _BASE_FIELDS and v}
    return Component(
        id=form.get("id", ""),
        component_type=component_type,
        mpn=form.get("mpn", ""),
        manufacturer=form.get("manufacturer", ""),
        description=form.get("description", ""),
        symbol=form.get("symbol", ""),
        footprint=form.get("footprint", ""),
        lifecycle_status=form.get("lifecycle_status", "active"),
        value=form.get("value", ""),
        tolerance=form.get("tolerance", ""),
        package=form.get("package", ""),
        rated_voltage=form.get("rated_voltage", ""),
        operating_temp=form.get("operating_temp", ""),
        datasheet=form.get("datasheet", ""),
        supplier=form.get("supplier", ""),
        supplier_sku=form.get("supplier_sku", ""),
        notes=form.get("notes", ""),
        keywords=form.get("keywords", ""),
        exclude_from_bom=form.get("exclude_from_bom", "0"),
        extra_fields=extra,
    )


def _custom_param_context(component: Component) -> tuple[list[str], dict[str, str]]:
    """Returns (suggested_names, existing_unmapped) for the custom-params UI.

    Suggestions are existing extra-field names used by other parts of the same
    type, minus anything already promoted to the schema. Existing-unmapped is
    this component's extras minus its schema fields, used to pre-render rows.
    """
    types = get_component_types()
    type_info = types.get(component.component_type, {})
    schema_field_names = {f["name"] for f in type_info.get("fields", [])}

    store = CSVStore()
    suggestions: set[str] = set()
    for comp in store.read_all(component.component_type):
        suggestions.update(comp.extra_fields.keys())
    suggestions -= schema_field_names
    suggestions -= _BASE_FIELDS

    existing_unmapped = {
        k: v
        for k, v in component.extra_fields.items()
        if k not in schema_field_names
    }
    return sorted(suggestions), existing_unmapped


def _render_form(
    request: Request,
    component: Component,
    errors: list[str] | None,
    is_edit: bool = False,
) -> HTMLResponse:
    types = get_component_types()
    suggested_extras, existing_unmapped = _custom_param_context(component)
    env = request.app.state.jinja_env
    template = env.get_template("components/form.html")
    return HTMLResponse(template.render(
        request=request,
        component=component,
        component_type=component.component_type,
        type_info=types.get(component.component_type, {}),
        next_id=component.id,
        columns=get_columns(),
        common_symbol=get_common_symbol(component.component_type) or "",
        errors=errors,
        is_edit=is_edit,
        suggested_extras=suggested_extras,
        existing_unmapped=existing_unmapped,
    ))


def _validate(component: Component) -> list[str]:
    errors = []
    prefix = get_id_prefix(component.component_type)

    if not component.id:
        errors.append("ID is required")
    elif not component.id.startswith(prefix):
        errors.append(f"ID must start with {prefix}-")

    if not component.mpn:
        errors.append("MPN is required")
    if not component.manufacturer:
        errors.append("Manufacturer is required")
    if not component.description:
        errors.append("Description is required")

    if component.symbol and ":" not in component.symbol:
        errors.append("Symbol must be in Library:Name format")
    if component.footprint and ":" not in component.footprint:
        errors.append("Footprint must be in Library:Name format")

    if component.lifecycle_status not in ("active", "deprecated", "obsolete"):
        errors.append("Lifecycle status must be active, deprecated, or obsolete")

    return errors


@router.get("/", response_class=HTMLResponse)
def list_components(request: Request, component_type: str | None = None):
    store = CSVStore()
    types = get_component_types()

    if component_type and component_type in types:
        components = store.read_all(component_type)
    else:
        all_components = store.read_all_types()
        components = []
        for comps in all_components.values():
            components.extend(comps)
        components.sort(key=lambda c: c.id)
        component_type = None

    env = request.app.state.jinja_env
    template = env.get_template("components/list.html")
    return HTMLResponse(template.render(
        request=request,
        components=components,
        component_type=component_type,
        component_types=types,
    ))


@router.get("/new", response_class=HTMLResponse)
def new_component_form(request: Request, component_type: str):
    types = get_component_types()
    if component_type not in types:
        return RedirectResponse(url="/components", status_code=303)

    store = CSVStore()
    next_id = store.get_next_id(component_type)
    stub = Component(
        id=next_id,
        component_type=component_type,
        mpn="", manufacturer="", description="", symbol="", footprint="",
    )
    return _render_form(request, stub, errors=None, is_edit=False)


@router.post("/", response_class=HTMLResponse)
async def create_component(request: Request):
    form = dict(await request.form())
    component_type = form.get("component_type", "")
    types = get_component_types()

    if component_type not in types:
        return RedirectResponse(url="/components", status_code=303)

    component = _component_from_form(form, component_type)
    errors = _validate(component)
    if errors:
        return _render_form(request, component, errors, is_edit=False)

    store = CSVStore()
    store.save(component)
    update_component_db(component)
    return RedirectResponse(url=f"/components?component_type={component_type}", status_code=303)


@router.get("/{component_type}/{part_id}", response_class=HTMLResponse)
def view_component(request: Request, component_type: str, part_id: str):
    types = get_component_types()
    if component_type not in types:
        return RedirectResponse(url="/components", status_code=303)

    store = CSVStore()
    component = store.get_by_id(component_type, part_id)
    if not component:
        return RedirectResponse(url=f"/components?component_type={component_type}", status_code=303)

    env = request.app.state.jinja_env
    template = env.get_template("components/detail.html")
    return HTMLResponse(template.render(
        request=request,
        component=component,
        component_type=component_type,
        type_info=types[component_type],
        component_types=types,
    ))


@router.get("/{component_type}/{part_id}/edit", response_class=HTMLResponse)
def edit_component_form(request: Request, component_type: str, part_id: str):
    types = get_component_types()
    if component_type not in types:
        return RedirectResponse(url="/components", status_code=303)

    store = CSVStore()
    component = store.get_by_id(component_type, part_id)
    if not component:
        return RedirectResponse(url=f"/components?component_type={component_type}", status_code=303)

    return _render_form(request, component, errors=None, is_edit=True)


@router.post("/{component_type}/{part_id}", response_class=HTMLResponse)
async def update_component(request: Request, component_type: str, part_id: str):
    types = get_component_types()
    if component_type not in types:
        return RedirectResponse(url="/components", status_code=303)

    form = dict(await request.form())
    component = _component_from_form(form, component_type)
    errors = _validate(component)
    if errors:
        return _render_form(request, component, errors, is_edit=True)

    store = CSVStore()
    store.save(component)
    update_component_db(component)
    return RedirectResponse(url=f"/components?component_type={component_type}", status_code=303)


@router.get("/{component_type}/{part_id}/delete", response_class=HTMLResponse)
def delete_component_form(request: Request, component_type: str, part_id: str):
    types = get_component_types()
    if component_type not in types:
        return RedirectResponse(url="/components", status_code=303)

    store = CSVStore()
    component = store.get_by_id(component_type, part_id)
    if not component:
        return RedirectResponse(url=f"/components?component_type={component_type}", status_code=303)

    env = request.app.state.jinja_env
    template = env.get_template("components/delete.html")
    return HTMLResponse(template.render(
        request=request,
        component=component,
        component_type=component_type,
        type_info=types[component_type],
    ))


@router.post("/{component_type}/{part_id}/delete", response_class=HTMLResponse)
def delete_component(request: Request, component_type: str, part_id: str):
    store = CSVStore()
    store.delete(component_type, part_id)
    delete_from_db(component_type, part_id)
    return RedirectResponse(url=f"/components?component_type={component_type}", status_code=303)
