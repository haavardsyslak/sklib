"""On-demand JSON endpoints for repo-local KiCad libraries.

System libraries are served as static JSON (built by scripts/build_indexes.py)
because they're large and rarely change. Repo libraries change every time the
user draws a new symbol, so we scan them on demand and cache by file mtime.
"""

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter

from src.web.kicad_paths import get_repo_paths
from src.web.symbol_index import scan_repo_footprints, scan_repo_symbols

router = APIRouter()

_symbol_cache: tuple[tuple, list] | None = None
_footprint_cache: tuple[tuple, list] | None = None


def _signature(paths: list[Path]) -> tuple:
    items: list[tuple[str, float]] = []
    for p in paths:
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file():
                    try:
                        items.append((str(child), child.stat().st_mtime))
                    except OSError:
                        pass
        elif p.is_file():
            try:
                items.append((str(p), p.stat().st_mtime))
            except OSError:
                pass
    return tuple(items)


@router.get("/api/repo/symbols")
def repo_symbols() -> list[dict]:
    global _symbol_cache
    sig = _signature(get_repo_paths().get("symbols", []))
    if _symbol_cache and _symbol_cache[0] == sig:
        return _symbol_cache[1]
    entries = [
        asdict(e)
        for e in sorted(scan_repo_symbols(), key=lambda x: x.full_name)
    ]
    _symbol_cache = (sig, entries)
    return entries


@router.get("/api/repo/footprints")
def repo_footprints() -> list[dict]:
    global _footprint_cache
    sig = _signature(get_repo_paths().get("footprints", []))
    if _footprint_cache and _footprint_cache[0] == sig:
        return _footprint_cache[1]
    entries = [
        asdict(e)
        for e in sorted(scan_repo_footprints(), key=lambda x: x.full_name)
    ]
    _footprint_cache = (sig, entries)
    return entries
