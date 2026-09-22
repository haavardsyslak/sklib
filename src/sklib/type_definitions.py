import re
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from sklib.models import Scalar

FieldKind = Literal["string", "integer", "number", "boolean", "enum"]

_COMMON_VALUE_FIELDS = {"mpn"}

_RESERVED_SPEC_FIELDS = {
    "id",
    "component_type",
    "mpn",
    "manufacturer",
    "description",
    "value",
    "symbol",
    "footprint",
    "datasheet",
    "keywords",
    "manufacturer_status",
    "notes",
    "exclude_from_bom",
    "supplier",
    "supplier_sku",
    "supplier_url",
}


class TypeDefinitionError(ValueError):
    """Raised when component-type definitions cannot be loaded."""


class FieldDefinition(BaseModel):
    """Declarative specification field used by validation and forms."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    kind: FieldKind = "string"
    required: bool = False
    options: list[str] = Field(default_factory=list)
    pattern: str = ""
    placeholder: str = ""
    help: str = ""

    @model_validator(mode="after")
    def validate_options(self) -> "FieldDefinition":
        if self.kind == "enum" and not self.options:
            raise ValueError("enum fields require options")
        if self.kind != "enum" and self.options:
            raise ValueError("options are only valid for enum fields")
        if any(not option.strip() for option in self.options):
            raise ValueError("enum options cannot be empty")
        if len(self.options) != len(set(self.options)):
            raise ValueError("enum options must be unique")
        if self.pattern:
            try:
                re.compile(self.pattern)
            except re.error as error:
                raise ValueError(f"invalid pattern: {error}") from error
        return self


class ComponentTypeDefinition(BaseModel):
    """Declarative definition of one component type."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    plural: str = Field(min_length=1)
    prefix: str = Field(pattern=r"^[A-Z]{2,4}$")
    value_field: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    default_symbol: str = ""
    fields: list[FieldDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_fields(self) -> "ComponentTypeDefinition":
        names = [field.name for field in self.fields]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate fields: {', '.join(duplicates)}")
        reserved = sorted(set(names) & _RESERVED_SPEC_FIELDS)
        if reserved:
            raise ValueError(f"reserved fields: {', '.join(reserved)}")
        if self.value_field not in _COMMON_VALUE_FIELDS:
            if self.value_field not in names:
                raise ValueError(f"value_field '{self.value_field}' is not defined")
            value_definition = next(
                field for field in self.fields if field.name == self.value_field
            )
            if not value_definition.required:
                raise ValueError("value_field must be required")
        if self.default_symbol and not re.fullmatch(
            r"[^:\s]+:[^:\s]+", self.default_symbol
        ):
            raise ValueError("default_symbol must use Library:Name format")
        return self

    def field(self, name: str) -> FieldDefinition | None:
        return next((field for field in self.fields if field.name == name), None)

    def validate_specs(self, specs: dict[str, Scalar]) -> list[str]:
        errors: list[str] = []
        definitions = {field.name: field for field in self.fields}
        for name in sorted(set(specs) - set(definitions)):
            errors.append(f"specs.{name}: unknown field")

        for definition in self.fields:
            value = specs.get(definition.name)
            if value is None or value == "":
                if definition.required:
                    errors.append(f"specs.{definition.name}: field is required")
                continue
            error = _validate_field_value(definition, value)
            if error:
                errors.append(f"specs.{definition.name}: {error}")
        return errors


class TypeRegistry:
    """Loaded component-type definitions indexed by name."""

    def __init__(self, definitions: dict[str, ComponentTypeDefinition]) -> None:
        self._definitions = definitions

    def __iter__(self) -> Iterator[ComponentTypeDefinition]:
        return iter(self._definitions.values())

    def __len__(self) -> int:
        return len(self._definitions)

    def get(self, name: str) -> ComponentTypeDefinition | None:
        return self._definitions.get(name)

    def require(self, name: str) -> ComponentTypeDefinition:
        definition = self.get(name)
        if definition is None:
            raise TypeDefinitionError(f"Unknown component type: {name}")
        return definition

    @classmethod
    def load(cls, directory: Path) -> "TypeRegistry":
        if not directory.is_dir():
            raise TypeDefinitionError(
                f"Type definitions directory not found: {directory}"
            )

        definitions: dict[str, ComponentTypeDefinition] = {}
        prefixes: dict[str, str] = {}
        paths = sorted(directory.glob("*.toml"))
        if not paths:
            raise TypeDefinitionError(f"No type definitions found in {directory}")

        for path in paths:
            try:
                with open(path, "rb") as file:
                    data = tomllib.load(file)
                definition = ComponentTypeDefinition.model_validate(data)
            except (OSError, tomllib.TOMLDecodeError, ValidationError) as error:
                raise TypeDefinitionError(
                    f"Invalid type definition {path}: {error}"
                ) from error

            if path.stem != definition.name:
                raise TypeDefinitionError(
                    f"Type definition filename {path.name} must match "
                    f"name '{definition.name}'"
                )
            if definition.name in definitions:
                raise TypeDefinitionError(
                    f"Duplicate component type: {definition.name}"
                )
            existing = prefixes.get(definition.prefix)
            if existing:
                raise TypeDefinitionError(
                    f"Prefix {definition.prefix} is shared by {existing} and "
                    f"{definition.name}"
                )
            definitions[definition.name] = definition
            prefixes[definition.prefix] = definition.name

        return cls(definitions)


def _validate_field_value(definition: FieldDefinition, value: Scalar) -> str | None:
    if definition.kind in {"string", "enum"} and not isinstance(value, str):
        return "must be a string"
    if definition.kind == "integer" and (
        not isinstance(value, int) or isinstance(value, bool)
    ):
        return "must be an integer"
    if definition.kind == "number" and (
        not isinstance(value, (int, float)) or isinstance(value, bool)
    ):
        return "must be a number"
    if definition.kind == "boolean" and not isinstance(value, bool):
        return "must be a boolean"
    if definition.kind == "enum" and value not in definition.options:
        return f"must be one of: {', '.join(definition.options)}"
    if definition.pattern and isinstance(value, str):
        if not re.fullmatch(definition.pattern, value):
            return f"must match pattern {definition.pattern}"
    return None
