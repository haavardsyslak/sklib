import os
import secrets
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomlkit
from pydantic import ValidationError

from sklib.config import Workspace
from sklib.models import Part
from sklib.type_definitions import ComponentTypeDefinition, TypeRegistry

_ID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ID_GROUP_LENGTH = 5
_ID_GENERATION_ATTEMPTS = 100


@dataclass(frozen=True)
class ValidationIssue:
    """One actionable problem in a catalog."""

    path: Path
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class CatalogError(ValueError):
    """Raised when a catalog operation would produce invalid data."""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        super().__init__("\n".join(str(issue) for issue in issues))


class Catalog:
    """Read, validate, and atomically write canonical part records."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.types = TypeRegistry.load(workspace.types_dir)

    def part_path(self, part: Part) -> Path:
        return self.workspace.parts_dir / part.component_type / f"{part.id}.toml"

    def scan(self) -> tuple[list[Part], list[ValidationIssue]]:
        parts: list[Part] = []
        issues: list[ValidationIssue] = []
        if not self.workspace.parts_dir.exists():
            return parts, issues

        for path in sorted(self.workspace.parts_dir.rglob("*.toml")):
            part, path_issues = self._load_path(path)
            issues.extend(path_issues)
            if part is not None:
                parts.append(part)

        issues.extend(self._duplicate_issues(parts))
        return sorted(parts, key=lambda part: part.id), issues

    def load_all(self) -> list[Part]:
        parts, issues = self.scan()
        if issues:
            raise CatalogError(issues)
        return parts

    def get(self, component_type: str, part_id: str) -> Part | None:
        definition = self.types.get(component_type)
        if definition is None or not re_full_id(definition, part_id):
            return None
        path = self.workspace.parts_dir / component_type / f"{part_id}.toml"
        if not path.is_file():
            return None
        part, issues = self._load_path(path)
        if issues or part is None:
            raise CatalogError(issues)
        return part

    def new_id(self, component_type: str) -> str:
        definition = self.types.require(component_type)
        directory = self.workspace.parts_dir / component_type
        for _ in range(_ID_GENERATION_ATTEMPTS):
            suffix = _random_id_suffix()
            part_id = (
                f"{definition.prefix}-{suffix[:_ID_GROUP_LENGTH]}-"
                f"{suffix[_ID_GROUP_LENGTH:]}"
            )
            if not (directory / f"{part_id}.toml").exists():
                return part_id
        raise CatalogError(
            [
                ValidationIssue(
                    directory,
                    "could not generate an unused component ID; try again",
                )
            ]
        )

    def save(self, part: Part, original_id: str | None = None) -> Path:
        issues = self._part_issues(part, self.part_path(part), check_path=False)
        parts, scan_issues = self.scan()
        issues.extend(scan_issues)

        identity = _part_identity(part)
        for existing in parts:
            if original_id is not None and existing.id == original_id:
                continue
            if existing.id.casefold() == part.id.casefold():
                issues.append(
                    ValidationIssue(
                        self.part_path(existing), f"duplicate ID '{part.id}'"
                    )
                )
            if _part_identity(existing) == identity:
                issues.append(
                    ValidationIssue(
                        self.part_path(existing),
                        f"duplicate manufacturer and MPN ({existing.id})",
                    )
                )

        if original_id is not None and original_id != part.id:
            issues.append(
                ValidationIssue(self.part_path(part), "component ID cannot be changed")
            )
        if issues:
            raise CatalogError(issues)

        definition = self.types.require(part.component_type)
        path = self.part_path(part)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing_text = path.read_text(encoding="utf-8") if path.exists() else None
        document = _update_document(existing_text, part, definition)
        _atomic_write(path, tomlkit.dumps(document))
        return path

    def delete(self, component_type: str, part_id: str) -> bool:
        definition = self.types.get(component_type)
        if definition is None or not re_full_id(definition, part_id):
            return False
        path = self.workspace.parts_dir / component_type / f"{part_id}.toml"
        if not path.is_file():
            return False
        path.unlink()
        try:
            path.parent.rmdir()
        except OSError:
            pass
        return True

    def _load_path(self, path: Path) -> tuple[Part | None, list[ValidationIssue]]:
        try:
            with open(path, "rb") as file:
                data = tomllib.load(file)
            part = Part.model_validate(data)
        except (OSError, tomllib.TOMLDecodeError) as error:
            return None, [ValidationIssue(path, str(error))]
        except ValidationError as error:
            return None, _pydantic_issues(path, error)

        issues = self._part_issues(part, path, check_path=True)
        return part, issues

    def _part_issues(
        self, part: Part, path: Path, check_path: bool
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        definition = self.types.get(part.component_type)
        if definition is None:
            return [
                ValidationIssue(path, f"unknown component type '{part.component_type}'")
            ]

        if not re_full_id(definition, part.id):
            issues.append(
                ValidationIssue(
                    path,
                    f"ID must use {definition.prefix}-XXXXX-XXXXX format "
                    "or a legacy numeric ID",
                )
            )
        for message in definition.validate_specs(part.specs):
            issues.append(ValidationIssue(path, message))

        if check_path:
            expected = self.part_path(part)
            expected_relative = expected.relative_to(self.workspace.parts_dir)
            try:
                actual_relative = path.relative_to(self.workspace.parts_dir)
            except ValueError:
                actual_relative = path
            if actual_relative.parts != expected_relative.parts:
                issues.append(
                    ValidationIssue(
                        path,
                        "record must be stored at "
                        f"{expected.relative_to(self.workspace.root)}",
                    )
                )
        return issues

    def _duplicate_issues(self, parts: list[Part]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        ids: dict[str, Part] = {}
        identities: dict[tuple[str, str], Part] = {}
        for part in parts:
            normalized_id = part.id.casefold()
            if normalized_id in ids:
                first = ids[normalized_id]
                issues.append(
                    ValidationIssue(
                        self.part_path(part), f"duplicate ID also used by {first.id}"
                    )
                )
            else:
                ids[normalized_id] = part

            identity = _part_identity(part)
            if identity in identities:
                first = identities[identity]
                issues.append(
                    ValidationIssue(
                        self.part_path(part),
                        f"manufacturer and MPN also used by {first.id}",
                    )
                )
            else:
                identities[identity] = part
        return issues


def re_full_id(definition: ComponentTypeDefinition, part_id: str) -> bool:
    prefix, separator, suffix = part_id.partition("-")
    if separator != "-" or prefix != definition.prefix:
        return False
    if len(suffix) >= 4 and suffix.isdigit():
        return True
    groups = suffix.split("-")
    return len(groups) == 2 and all(
        len(group) == _ID_GROUP_LENGTH
        and all(character in _ID_ALPHABET for character in group)
        for group in groups
    )


def _random_id_suffix() -> str:
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_GROUP_LENGTH * 2))


def _part_identity(part: Part) -> tuple[str, str]:
    return part.manufacturer.strip().casefold(), part.mpn.strip().casefold()


def _pydantic_issues(path: Path, error: ValidationError) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for item in error.errors(include_url=False):
        location = ".".join(str(value) for value in item["loc"])
        prefix = f"{location}: " if location else ""
        issues.append(ValidationIssue(path, f"{prefix}{item['msg']}"))
    return issues


def _update_document(
    existing_text: str | None,
    part: Part,
    definition: ComponentTypeDefinition,
) -> tomlkit.TOMLDocument:
    document = tomlkit.parse(existing_text) if existing_text else tomlkit.document()
    root_values: dict[str, Any] = {
        "schema_version": part.schema_version,
        "id": part.id,
        "component_type": part.component_type,
        "mpn": part.mpn,
        "manufacturer": part.manufacturer,
        "description": part.description,
        "manufacturer_status": part.manufacturer_status,
        "datasheet": part.datasheet,
        "keywords": part.keywords,
        "notes": part.notes,
    }
    optional_root = {"datasheet", "keywords", "notes"}
    for key, value in root_values.items():
        if key in optional_root and not value:
            if key in document:
                del document[key]
        else:
            document[key] = value

    _sync_table(
        document,
        "kicad",
        {
            "symbol": part.kicad.symbol,
            "footprint": part.kicad.footprint,
            "exclude_from_bom": part.kicad.exclude_from_bom,
        },
        optional={"exclude_from_bom"},
    )
    ordered_specs = {
        field.name: part.specs[field.name]
        for field in definition.fields
        if field.name in part.specs and part.specs[field.name] != ""
    }
    _sync_table(document, "specs", ordered_specs)

    if part.suppliers:
        suppliers = tomlkit.aot()
        for supplier in part.suppliers:
            table = tomlkit.table()
            table["name"] = supplier.name
            table["sku"] = supplier.sku
            if supplier.product_url:
                table["product_url"] = supplier.product_url
            suppliers.append(table)
        document["suppliers"] = suppliers
    elif "suppliers" in document:
        del document["suppliers"]

    return document


def _sync_table(
    document: tomlkit.TOMLDocument,
    name: str,
    values: dict[str, Any],
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    table = document.get(name)
    if not isinstance(table, dict):
        table = tomlkit.table()
        document[name] = table
    for key in list(table):
        if key not in values or (key in optional and not values[key]):
            del table[key]
    for key, value in values.items():
        if key not in optional or value:
            table[key] = value


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
