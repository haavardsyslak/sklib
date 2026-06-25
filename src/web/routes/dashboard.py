from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.web.csv_store import CSVStore
from src.web.schema import get_component_types

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    store = CSVStore()
    stats = store.get_stats()
    env = request.app.state.jinja_env
    template = env.get_template("dashboard.html")
    return HTMLResponse(template.render(
        request=request,
        stats=stats,
        component_types=get_component_types(),
    ))
