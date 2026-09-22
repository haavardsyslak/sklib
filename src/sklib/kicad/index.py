import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sklib.config import Workspace
from sklib.kicad.paths import detect_system_paths


@dataclass(frozen=True)
class LibraryEntry:
    """Searchable KiCad symbol or footprint."""

    library: str
    name: str
    source: str
    properties: dict[str, str] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.library}:{self.name}"


def load_symbols(workspace: Workspace) -> list[LibraryEntry]:
    system = detect_system_paths().symbols
    entries = _load_system_cache(
        workspace.cache_dir / "symbols.json",
        system,
        _scan_symbol_directory,
    )
    entries.extend(_scan_repo_symbols(workspace.kicad_dir))
    return _deduplicate(entries)


def load_footprints(workspace: Workspace) -> list[LibraryEntry]:
    system = detect_system_paths().footprints
    entries = _load_system_cache(
        workspace.cache_dir / "footprints.json",
        system,
        _scan_footprint_directory,
    )
    entries.extend(_scan_repo_footprints(workspace.kicad_dir))
    return _deduplicate(entries)


def _load_system_cache(
    cache_path: Path,
    directory: Path | None,
    scanner: Callable[[Path, str], list[LibraryEntry]],
) -> list[LibraryEntry]:
    if directory is None:
        return []
    fingerprint = {
        "path": str(directory.resolve()),
        "mtime_ns": directory.stat().st_mtime_ns,
    }
    if cache_path.is_file():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if data.get("fingerprint") == fingerprint:
                return [LibraryEntry(**item) for item in data.get("entries", [])]
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    entries = scanner(directory, "system")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "fingerprint": fingerprint,
                "entries": [asdict(entry) for entry in entries],
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    return entries


def _scan_repo_symbols(directory: Path) -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    if directory.is_dir():
        for path in sorted(directory.rglob("*.kicad_sym")):
            entries.extend(_parse_symbol_file(path, "repo"))
    return entries


def _scan_repo_footprints(directory: Path) -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    if directory.is_dir():
        for path in sorted(directory.rglob("*.pretty")):
            entries.extend(_parse_footprint_library(path, "repo"))
    return entries


def _scan_symbol_directory(directory: Path, source: str) -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    for path in sorted(directory.glob("*.kicad_sym")):
        entries.extend(_parse_symbol_file(path, source))
    return entries


def _scan_footprint_directory(directory: Path, source: str) -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    for path in sorted(directory.glob("*.pretty")):
        entries.extend(_parse_footprint_library(path, source))
    return entries


def _parse_symbol_file(path: Path, source: str) -> list[LibraryEntry]:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    entries: list[LibraryEntry] = []
    for match in re.finditer(r'\(symbol\s+"([^"]+)"', content):
        name = match.group(1)
        suffix = name.rsplit("_", 1)[-1] if "_" in name else ""
        if suffix.isdigit() or (len(suffix) > 1 and suffix[:-1].isdigit()):
            continue
        block = _balanced_expression(content, match.start())
        properties = {
            key: value
            for key, value in re.findall(r'\(property\s+"([^"]+)"\s+"([^"]*)"', block)
            if value.strip() and key not in {"Reference", "Value"}
        }
        entries.append(
            LibraryEntry(
                library=path.stem,
                name=name,
                source=source,
                properties=properties,
            )
        )
    return entries


def _balanced_expression(content: str, start: int) -> str:
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(content)):
        character = content[index]
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"':
            quoted = not quoted
        elif not quoted and character == "(":
            depth += 1
        elif not quoted and character == ")":
            depth -= 1
            if depth == 0:
                return content[start : index + 1]
    return content[start:]


def _parse_footprint_library(path: Path, source: str) -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    for footprint in sorted(path.glob("*.kicad_mod")):
        properties: dict[str, str] = {}
        try:
            content = footprint.read_text(encoding="utf-8")
            description = re.search(r'\(descr\s+"([^"]+)"', content)
            if description:
                properties["Description"] = description.group(1)
        except (OSError, UnicodeDecodeError):
            pass
        entries.append(
            LibraryEntry(
                library=path.stem,
                name=footprint.stem,
                source=source,
                properties=properties,
            )
        )
    return entries


def _deduplicate(entries: list[LibraryEntry]) -> list[LibraryEntry]:
    result: dict[str, LibraryEntry] = {}
    for entry in entries:
        key = entry.full_name.casefold()
        existing = result.get(key)
        if existing is None or entry.source == "repo":
            result[key] = entry
    return sorted(result.values(), key=lambda entry: entry.full_name)
