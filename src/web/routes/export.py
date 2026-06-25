import csv
from io import StringIO

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse

from src.web.csv_store import CSVStore
from src.web.schema import get_component_types


router = APIRouter()


@router.get("/csv", response_class=StreamingResponse)
def export_csv(request: Request, component_type: str | None = None):
    store = CSVStore()
    types = get_component_types()

    output = StringIO()

    if component_type and component_type in types:
        components = store.read_all(component_type)
        filename = f"{component_type}s.csv"
    else:
        all_components = store.read_all_types()
        components = []
        for comps in all_components.values():
            components.extend(comps)
        components.sort(key=lambda c: c.id)
        filename = "all_components.csv"

    if not components:
        raise HTTPException(status_code=404, detail="No components found")

    fieldnames = [
        "id",
        "component_type",
        "mpn",
        "manufacturer",
        "description",
        "symbol",
        "footprint",
        "lifecycle_status",
        "value",
        "tolerance",
        "package",
        "rated_voltage",
        "operating_temp",
        "datasheet",
        "supplier",
        "supplier_sku",
        "notes",
        "keywords",
        "exclude_from_bom",
    ]

    extra_fields = set()
    for comp in components:
        extra_fields.update(comp.extra_fields.keys())
    fieldnames.extend(sorted(extra_fields))

    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for comp in components:
        writer.writerow(comp.to_row())

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
