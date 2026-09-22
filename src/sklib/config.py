import os
import platform
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when workspace configuration is missing or invalid."""


@dataclass(frozen=True)
class Workspace:
    """Resolved paths and metadata for one component-library workspace."""

    root: Path
    name: str
    description: str
    parts_dir: Path
    types_dir: Path
    kicad_dir: Path
    generated_dir: Path

    @property
    def database_path(self) -> Path:
        return self.generated_dir / "sklib.db"

    @property
    def dbl_path(self) -> Path:
        return self.generated_dir / "sklib.kicad_dbl"

    @property
    def cache_dir(self) -> Path:
        return self.root / ".sklib" / "cache"

    @classmethod
    def load(cls, root: Path | str = ".") -> "Workspace":
        resolved_root = Path(root).expanduser().resolve()
        load_dotenv(resolved_root / ".env", override=False)
        config_path = resolved_root / "sklib.toml"
        if not config_path.is_file():
            raise ConfigurationError(f"Workspace config not found: {config_path}")

        try:
            with open(config_path, "rb") as file:
                document = tomllib.load(file)
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise ConfigurationError(
                f"Failed to read workspace config {config_path}: {error}"
            ) from error

        library = document.get("library", {})
        paths = document.get("paths", {})
        if not isinstance(library, dict) or not isinstance(paths, dict):
            raise ConfigurationError(
                f"Invalid workspace config {config_path}: expected tables"
            )
        _reject_unknown(config_path, document, {"library", "paths"}, "root")
        _reject_unknown(config_path, library, {"name", "description"}, "library")
        _reject_unknown(
            config_path,
            paths,
            {"parts", "types", "kicad", "generated"},
            "paths",
        )

        name = library.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigurationError(
                f"Invalid workspace config {config_path}: library.name is required"
            )

        def resolve_path(key: str, default: str) -> Path:
            value = paths.get(key, default)
            if not isinstance(value, str) or not value:
                raise ConfigurationError(
                    f"Invalid workspace config {config_path}: paths.{key}"
                )
            path = Path(value).expanduser()
            if path.is_absolute():
                return path.resolve()
            return (resolved_root / path).resolve()

        description = library.get("description", "")
        if not isinstance(description, str):
            raise ConfigurationError(
                f"Invalid workspace config {config_path}: "
                "library.description must be a string"
            )

        return cls(
            root=resolved_root,
            name=name.strip(),
            description=description.strip(),
            parts_dir=resolve_path("parts", "parts"),
            types_dir=resolve_path("types", "types"),
            kicad_dir=resolve_path("kicad", "kicad"),
            generated_dir=resolve_path("generated", "generated"),
        )

    def odbc_driver(self) -> str:
        configured = os.environ.get("SKLIB_ODBC_DRIVER")
        if configured:
            return configured
        return "SQLite3 ODBC Driver" if platform.system() == "Windows" else "SQLite3"


def _reject_unknown(
    path: Path,
    values: dict[str, object],
    allowed: set[str],
    section: str,
) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ConfigurationError(
            f"Invalid workspace config {path}: unknown {section} keys: "
            f"{', '.join(unknown)}"
        )
