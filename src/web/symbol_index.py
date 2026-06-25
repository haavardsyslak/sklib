"""Generate searchable indexes from KiCad libraries."""

import json
import re
from pathlib import Path
from dataclasses import dataclass, asdict, field

from src.web.kicad_paths import get_kicad_paths, get_repo_paths


@dataclass
class LibraryEntry:
    library: str
    name: str
    source: str = "system"
    properties: dict[str, str] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.library}:{self.name}"


def scan_system_symbols() -> list[LibraryEntry]:
    """Scan KiCad system symbol libraries (slow, change rarely)."""
    entries: list[LibraryEntry] = []
    paths = get_kicad_paths()
    if paths.system_symbols and paths.system_symbols.exists():
        for lib_file in paths.system_symbols.glob("*.kicad_sym"):
            entries.extend(_parse_symbol_file(lib_file, "system"))
    return entries


def scan_repo_symbols() -> list[LibraryEntry]:
    """Scan repo symbol libraries (fast, change with every new symbol)."""
    entries: list[LibraryEntry] = []
    for repo_file in get_repo_paths().get("symbols", []):
        entries.extend(_parse_symbol_file(repo_file, "repo"))
    return entries


def _extract_balanced_sexpr(content: str, start_pos: int) -> str:
    """Extract complete S-expression block with balanced parentheses."""
    depth = 0
    in_string = False
    escape = False

    for i in range(start_pos, len(content)):
        char = content[i]

        if escape:
            escape = False
            continue

        if char == "\\":
            escape = True
        elif char == '"':
            in_string = not in_string
        elif not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return content[start_pos : i + 1]

    return content[start_pos:]


def _extract_properties(symbol_block: str) -> dict[str, str]:
    """Extract all property key-value pairs from symbol block."""
    properties: dict[str, str] = {}

    for match in re.finditer(r'\(property\s+"([^"]+)"\s+"([^"]*)"', symbol_block):
        prop_name = match.group(1)
        prop_value = match.group(2)

        if prop_name in ["Reference", "Value"] or prop_name.startswith("Sim"):
            continue

        if prop_value.strip():
            properties[prop_name] = prop_value

    return properties


def _parse_symbol_file(path: Path, source: str) -> list[LibraryEntry]:
    """Parse a .kicad_sym file and extract all symbol properties."""
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    entries: list[LibraryEntry] = []
    library_name = path.stem

    symbol_pattern = r'\(symbol\s+"([^"]+)"'

    for sym_match in re.finditer(symbol_pattern, content):
        symbol_name = sym_match.group(1)

        if "_" in symbol_name:
            suffix = symbol_name.rsplit("_", 1)[-1]
            if suffix.isdigit() or (len(suffix) > 1 and suffix[:-1].isdigit()):
                continue

        symbol_block = _extract_balanced_sexpr(content, sym_match.start())
        properties = _extract_properties(symbol_block)

        entries.append(
            LibraryEntry(
                library=library_name,
                name=symbol_name,
                source=source,
                properties=properties,
            )
        )

    return entries


def scan_system_footprints() -> list[LibraryEntry]:
    """Scan KiCad system footprint libraries (slow, change rarely)."""
    entries: list[LibraryEntry] = []
    paths = get_kicad_paths()
    if paths.system_footprints and paths.system_footprints.exists():
        for lib_dir in paths.system_footprints.glob("*.pretty"):
            entries.extend(_parse_footprint_lib(lib_dir, "system"))
    return entries


def scan_repo_footprints() -> list[LibraryEntry]:
    """Scan repo footprint libraries (fast, change with every new footprint)."""
    entries: list[LibraryEntry] = []
    for repo_dir in get_repo_paths().get("footprints", []):
        entries.extend(_parse_footprint_lib(repo_dir, "repo"))
    return entries


def _parse_footprint_lib(lib_dir: Path, source: str) -> list[LibraryEntry]:
    """Parse a .pretty directory."""
    entries: list[LibraryEntry] = []
    library_name = lib_dir.stem

    for mod_file in lib_dir.glob("*.kicad_mod"):
        try:
            content = mod_file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            entries.append(
                LibraryEntry(library=library_name, name=mod_file.stem, source=source)
            )
            continue

        properties: dict[str, str] = {}
        desc_match = re.search(r'\(descr\s+"([^"]+)"', content)
        if desc_match:
            properties["Description"] = desc_match.group(1)

        entries.append(
            LibraryEntry(
                library=library_name,
                name=mod_file.stem,
                source=source,
                properties=properties,
            )
        )

    return entries


def _system_fingerprint() -> dict[str, object]:
    """Cheap sentinel for KiCad system libs.

    Uses directory mtime (updated by KiCad's installer when files are
    added/removed) plus the resolved path string so a path change
    triggers a rebuild too.
    """
    paths = get_kicad_paths()
    fp: dict[str, object] = {}
    for key, p in (("symbols", paths.system_symbols), ("footprints", paths.system_footprints)):
        if p and p.exists():
            try:
                fp[key] = {"path": str(p), "mtime_ns": p.stat().st_mtime_ns}
            except OSError:
                fp[key] = {"path": str(p), "mtime_ns": None}
        else:
            fp[key] = None
    return fp


def generate_indexes(output_dir: Path, force: bool = False) -> tuple[int, int]:
    """Build static JSON indexes for KiCad SYSTEM libraries only.

    Repo libraries are served live by `/api/repo/*` with an mtime cache,
    so they're intentionally excluded here to avoid duplicates.

    The scan is skipped when the system fingerprint (dir paths + mtimes)
    matches the value stored in `.system_meta.json` from the previous run.
    Pass `force=True` to bypass the check.

    Returns (symbol_count, footprint_count) — counts come from the cached
    files when the scan is skipped.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    meta_file = output_dir / ".system_meta.json"
    sym_file = output_dir / "symbols.json"
    fp_file = output_dir / "footprints.json"

    current_fp = _system_fingerprint()

    if not force and sym_file.exists() and fp_file.exists() and meta_file.exists():
        try:
            with open(meta_file, encoding="utf-8") as f:
                stored = json.load(f)
            if stored.get("fingerprint") == current_fp:
                return stored.get("sym_count", 0), stored.get("fp_count", 0)
        except (OSError, json.JSONDecodeError):
            pass

    symbols = scan_system_symbols()
    symbols_data = [asdict(s) for s in sorted(symbols, key=lambda x: x.full_name)]
    with open(sym_file, "w", encoding="utf-8") as f:
        json.dump(symbols_data, f, indent=2)

    footprints = scan_system_footprints()
    footprints_data = [asdict(f) for f in sorted(footprints, key=lambda x: x.full_name)]
    with open(fp_file, "w", encoding="utf-8") as f:
        json.dump(footprints_data, f, indent=2)

    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "fingerprint": current_fp,
                "sym_count": len(symbols),
                "fp_count": len(footprints),
            },
            f,
            indent=2,
        )

    return len(symbols), len(footprints)


def get_default_indexes_dir() -> Path:
    """Get the default indexes directory."""
    return Path(__file__).parent / "static" / "indexes"
