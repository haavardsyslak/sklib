import os
import platform
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KiCadPaths:
    """Detected system symbol and footprint directories."""

    symbols: Path | None
    footprints: Path | None


def detect_system_paths() -> KiCadPaths:
    """Find common KiCad system-library locations for current platform."""
    symbol_variables = [
        "KICAD_SYMBOL_DIR",
        *(f"KICAD{version}_SYMBOL_DIR" for version in range(10, 6, -1)),
    ]
    symbols = _environment_path(symbol_variables)
    footprints = _environment_path(
        [
            "KICAD_FOOTPRINT_DIR",
            *(f"KICAD{version}_FOOTPRINT_DIR" for version in range(10, 6, -1)),
        ]
    )

    system = platform.system()
    if system == "Linux":
        symbol_candidates = [
            Path("/usr/share/kicad/symbols"),
            Path("/usr/local/share/kicad/symbols"),
            Path("/opt/kicad/share/kicad/symbols"),
            Path.home() / ".local/share/kicad/symbols",
        ]
        footprint_candidates = [
            Path("/usr/share/kicad/footprints"),
            Path("/usr/local/share/kicad/footprints"),
            Path("/opt/kicad/share/kicad/footprints"),
            Path.home() / ".local/share/kicad/footprints",
        ]
    elif system == "Darwin":
        shared = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport")
        symbol_candidates = [shared / "symbols"]
        footprint_candidates = [shared / "footprints"]
    elif system == "Windows":
        roots = [
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "KiCad",
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
            / "KiCad",
        ]
        shares: list[Path] = []
        for root in roots:
            shares.append(root / "share" / "kicad")
            if root.is_dir():
                try:
                    children = sorted(root.iterdir(), reverse=True)
                except OSError:
                    children = []
                shares.extend(
                    child / "share" / "kicad" for child in children if child.is_dir()
                )
        symbol_candidates = [share / "symbols" for share in shares]
        footprint_candidates = [share / "footprints" for share in shares]
    else:
        symbol_candidates = []
        footprint_candidates = []

    return KiCadPaths(
        symbols=_first_existing(symbol_candidates, symbols),
        footprints=_first_existing(footprint_candidates, footprints),
    )


def _environment_path(names: list[str]) -> Path | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return Path(value)
    return None


def _first_existing(candidates: list[Path], override: Path | None) -> Path | None:
    if override is not None:
        return override.expanduser().resolve() if override.is_dir() else None
    return next((path for path in candidates if path.is_dir()), None)
