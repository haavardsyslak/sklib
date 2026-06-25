from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.web.routes import components, dashboard, export, library, supplier
from src.web.symbol_index import generate_indexes, get_default_indexes_dir


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        sym, fp = generate_indexes(get_default_indexes_dir())
        print(f"System index ready: {sym} symbols, {fp} footprints")
    except Exception as e:
        print(f"Warning: failed to build system index: {e}")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="SKLib - Syskals KiCad Library",
        description="Web UI for managing KiCad DBLib parts",
        version="0.2.0",
        lifespan=lifespan,
    )
    setup_templates(app)
    setup_static(app)
    setup_routes(app)

    return app


def setup_templates(app: FastAPI) -> None:
    from src.web.schema import load_schema

    templates_path = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_path)),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["component_types"] = load_schema().get("component_types", {})
    app.state.jinja_env = env


def setup_static(app: FastAPI) -> None:
    static_path = Path(__file__).parent / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


def setup_routes(app: FastAPI) -> None:
    app.include_router(components.router, prefix="/components", tags=["components"])
    app.include_router(dashboard.router, tags=["dashboard"])
    app.include_router(export.router, prefix="/export", tags=["export"])
    app.include_router(library.router, tags=["library"])
    app.include_router(supplier.router)

    @app.get("/")
    def root():
        return RedirectResponse(url="/components")


app = create_app()
