"""Cross-platform KiCad library path detection."""

from dataclasses import dataclass
from pathlib import Path
import platform
import os


@dataclass
class KiCadPaths:
    system_symbols: Path | None
    system_footprints: Path | None
    user_library: Path | None


def get_kicad_paths() -> KiCadPaths:
    """Detect KiCad library paths for current OS."""
    system = platform.system()

    if system == "Linux":
        return _get_linux_paths()
    elif system == "Darwin":
        return _get_macos_paths()
    elif system == "Windows":
        return _get_windows_paths()
    else:
        return KiCadPaths(
            system_symbols=None, system_footprints=None, user_library=None
        )


def get_repo_paths() -> dict[str, list[Path]]:
    """Get custom repo library paths."""
    repo_root = Path(__file__).parent.parent.parent
    paths: dict[str, list[Path]] = {"symbols": [], "footprints": []}

    kicad_dir = repo_root / "kicad"
    if kicad_dir.exists():
        for lib_file in kicad_dir.glob("*.kicad_sym"):
            paths["symbols"].append(lib_file)
        for lib_dir in kicad_dir.glob("*.pretty"):
            paths["footprints"].append(lib_dir)

    return paths


def _get_linux_paths() -> KiCadPaths:
    sym = os.environ.get("KICAD_SYMBOL_DIR")
    fp = os.environ.get("KICAD_FOOTPRINT_DIR")

    symbols = Path(sym) if sym else None
    footprints = Path(fp) if fp else None

    if not symbols:
        for p in [
            Path("/usr/share/kicad/symbols"),
            Path("/usr/share/kicad/library"),
            Path.home() / ".local/share/kicad/symbols",
            Path.home() / ".local/share/kicad/library",
            Path("/opt/kicad/share/kicad/symbols"),
            Path("/opt/kicad/share/kicad/library"),
        ]:
            if p.exists() and any(p.glob("*.kicad_sym")):
                symbols = p
                break

    if not footprints:
        for p in [
            Path("/usr/share/kicad/modules"),
            Path.home() / ".local/share/kicad/modules",
            Path("/usr/share/kicad/footprints"),
            Path("/opt/kicad/share/kicad/footprints"),
        ]:
            if p.exists():
                footprints = p
                break

    return KiCadPaths(
        system_symbols=symbols,
        system_footprints=footprints,
        user_library=Path.home() / ".local/share/kicad",
    )


def _get_macos_paths() -> KiCadPaths:
    symbols = None
    footprints = None

    kicad_app = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport")
    if kicad_app.exists():
        sym_path = kicad_app / "symbols"
        fp_path = kicad_app / "footprints"
        if sym_path.exists():
            symbols = sym_path
        if fp_path.exists():
            footprints = fp_path

    if not symbols or not footprints:
        user_path = Path.home() / "Library/Preferences/kicad"
        if not symbols:
            for p in [
                user_path / "symbols",
                Path.home() / ".local/share/kicad/symbols",
            ]:
                if (p / "Device.kicad_sym").exists():
                    symbols = p
                    break

    return KiCadPaths(
        system_symbols=symbols,
        system_footprints=footprints,
        user_library=Path.home() / "Library/Preferences/kicad",
    )


def _get_windows_paths() -> KiCadPaths:
    program_files = os.environ.get("ProgramFiles", "C:/Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")

    symbols = None
    footprints = None

    for base in [Path(program_files) / "KiCad", Path(program_files_x86) / "KiCad"]:
        share = base / "share" / "kicad"
        if not symbols and (share / "symbols").exists():
            symbols = share / "symbols"
        if not footprints and (share / "footprints").exists():
            footprints = share / "footprints"
        if not symbols and (share / "library").exists():
            symbols = share / "library"

    return KiCadPaths(
        system_symbols=symbols,
        system_footprints=footprints,
        user_library=Path(os.environ.get("APPDATA", "")) / "kicad",
    )
