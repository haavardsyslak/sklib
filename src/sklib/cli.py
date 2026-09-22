import argparse
import re
import shutil
import sqlite3
import sys
import time
from importlib import resources
from pathlib import Path

from sklib import __version__
from sklib.build import BuildError, build_catalog
from sklib.config import ConfigurationError, Workspace
from sklib.store import Catalog, CatalogError
from sklib.type_definitions import TypeDefinitionError


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sklib", description="Manage a Git-backed KiCad component library"
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Library workspace containing sklib.toml",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("check", help="Validate type definitions and all parts")
    commands.add_parser("build", help="Build SQLite DBLib artifacts")
    commands.add_parser("doctor", help="Check local workspace setup")
    commands.add_parser("index", help="Build local KiCad search indexes")

    new_id = commands.add_parser("new-id", help="Generate an ID for a type")
    new_id.add_argument("component_type")

    web = commands.add_parser("web", help="Run local web editor")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8000)

    initialize = commands.add_parser("init", help="Create a new library workspace")
    initialize.add_argument("path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return _initialize(args.path)

        workspace = Workspace.load(args.workspace)
        if args.command == "check":
            return _check(workspace)
        if args.command == "build":
            return _build(workspace)
        if args.command == "doctor":
            return _doctor(workspace)
        if args.command == "new-id":
            print(Catalog(workspace).new_id(args.component_type))
            return 0
        if args.command == "index":
            return _index(workspace)
        if args.command == "web":
            return _web(workspace, args.host, args.port)
    except (
        ConfigurationError,
        TypeDefinitionError,
        CatalogError,
        BuildError,
        OSError,
        sqlite3.Error,
    ) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 1


def _check(workspace: Workspace) -> int:
    catalog = Catalog(workspace)
    parts, issues = catalog.scan()
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}")
        print(f"Check failed: {len(issues)} error(s)", file=sys.stderr)
        return 1
    print(f"Check OK: {len(parts)} parts, {len(catalog.types)} component types")
    return 0


def _build(workspace: Workspace) -> int:
    result = build_catalog(workspace)
    print(
        f"Built {result.part_count} parts in {result.table_count} tables "
        f"in {result.elapsed_seconds:.3f}s"
    )
    print(f"Database: {result.database_path}")
    print(f"DBLib: {result.dbl_path}")
    return 0


def _doctor(workspace: Workspace) -> int:
    from sklib.kicad.paths import detect_system_paths

    print(f"Workspace: {workspace.root}")
    print(f"Library: {workspace.name}")
    checks = [
        ("Parts", workspace.parts_dir, False),
        ("Types", workspace.types_dir, True),
        ("KiCad assets", workspace.kicad_dir, False),
        ("Generated", workspace.generated_dir, False),
    ]
    failed = False
    for label, path, required in checks:
        exists = path.is_dir()
        state = "OK" if exists else "MISSING" if required else "CREATED WHEN NEEDED"
        print(f"{label}: {state} ({path})")
        failed = failed or (required and not exists)

    catalog = Catalog(workspace)
    parts, issues = catalog.scan()
    if issues:
        failed = True
        for issue in issues:
            print(f"Catalog: ERROR ({issue})")
    else:
        print(f"Catalog: OK ({len(parts)} parts)")

    system_paths = detect_system_paths()
    symbol_state = system_paths.symbols or "NOT FOUND; manual references still work"
    footprint_state = (
        system_paths.footprints or "NOT FOUND; manual references still work"
    )
    print(f"System symbols: {symbol_state}")
    print(f"System footprints: {footprint_state}")
    print(f"ODBC driver: {workspace.odbc_driver()} (not probed)")
    return 1 if failed else 0


def _index(workspace: Workspace) -> int:
    from sklib.kicad.index import load_footprints, load_symbols

    started = time.perf_counter()
    symbols = load_symbols(workspace, show_progress=True)
    footprints = load_footprints(workspace, show_progress=True)
    elapsed = time.perf_counter() - started
    print(
        f"Indexed {len(symbols)} symbols and {len(footprints)} footprints "
        f"in {elapsed:.3f}s"
    )
    print(f"Cache: {workspace.cache_dir}")
    return 0


def _web(workspace: Workspace, host: str, port: int) -> int:
    import uvicorn

    from sklib.web.app import create_app

    if host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            "Warning: web editor has no authentication and can modify files. "
            "Do not expose it without an authenticated reverse proxy.",
            file=sys.stderr,
        )
    uvicorn.run(create_app(workspace), host=host, port=port)
    return 0


def _initialize(path: Path) -> int:
    destination = path.expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        print(f"Error: destination is not empty: {destination}", file=sys.stderr)
        return 1
    destination.mkdir(parents=True, exist_ok=True)
    template = resources.files("sklib") / "templates" / "workspace"
    for item in template.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copyfile(item, target)
    project_name = re.sub(r"[^a-z0-9]+", "-", destination.name.casefold()).strip("-")
    if not project_name:
        project_name = "kicad-parts"
    pyproject = destination / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(
            'name = "my-kicad-parts"', f'name = "{project_name}"'
        ),
        encoding="utf-8",
    )
    config = destination / "sklib.toml"
    library_name = destination.name.replace("-", " ").replace("_", " ").title()
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            'name = "My KiCad Parts"', f'name = "{library_name}"'
        ),
        encoding="utf-8",
    )
    for directory in ("parts", "kicad", "generated"):
        (destination / directory).mkdir(exist_ok=True)
    (destination / ".gitignore").write_text(
        "/.sklib/\n/generated/\n/.env\n/.venv/\n__pycache__/\n*.py[cod]\n",
        encoding="utf-8",
    )
    print(f"Initialized SKLib workspace: {destination}")
    print("Next: open a terminal there, then run 'uv sync' and 'uv run sklib doctor'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
