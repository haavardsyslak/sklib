import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

type Scalar = str | int | float | bool
type ManufacturerStatus = Literal["active", "not_recommended", "obsolete", "unknown"]

_KICAD_REFERENCE = re.compile(r"^[^:\s]+:[^:\s]+$")


class KicadMapping(BaseModel):
    """KiCad symbol and footprint assigned to a component."""

    model_config = ConfigDict(extra="forbid", strict=True)

    symbol: str = Field(min_length=1)
    footprint: str = Field(min_length=1)
    exclude_from_bom: bool = False

    @field_validator("symbol", "footprint")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        value = value.strip()
        if not _KICAD_REFERENCE.fullmatch(value):
            raise ValueError("must use Library:Name format")
        return value


class SupplierReference(BaseModel):
    """Stable reference to one supplier listing."""

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    product_url: str = ""

    @field_validator("name", "sku")
    @classmethod
    def strip_required(cls, value: str) -> str:
        return value.strip()

    @field_validator("product_url")
    @classmethod
    def validate_product_url(cls, value: str) -> str:
        value = value.strip()
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("must be an http(s) URL")
        return value


class Part(BaseModel):
    """Stable structure shared by every canonical part record."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    id: str = Field(
        pattern=(
            r"^[A-Z]{2,4}-(\d{4,}|"
            r"[0-9A-HJKMNP-TV-Z]{5}-[0-9A-HJKMNP-TV-Z]{5})$"
        )
    )
    component_type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    mpn: str = Field(min_length=1)
    manufacturer: str = Field(min_length=1)
    description: str = Field(min_length=1)
    manufacturer_status: ManufacturerStatus = "active"
    datasheet: str = ""
    keywords: list[str] = Field(default_factory=list)
    notes: str = ""
    kicad: KicadMapping
    specs: dict[str, Scalar]
    suppliers: list[SupplierReference] = Field(default_factory=list)

    @field_validator("id", "component_type", "mpn", "manufacturer", "description")
    @classmethod
    def strip_required(cls, value: str) -> str:
        return value.strip()

    @field_validator("datasheet")
    @classmethod
    def validate_datasheet(cls, value: str) -> str:
        value = value.strip()
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("must be an http(s) URL")
        return value

    @field_validator("specs")
    @classmethod
    def validate_property_names(cls, values: dict[str, Scalar]) -> dict[str, Scalar]:
        invalid = sorted(
            name for name in values if not re.fullmatch(r"[a-z][a-z0-9_]*", name)
        )
        if invalid:
            raise ValueError(f"field names must use snake_case: {', '.join(invalid)}")
        return values

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            keyword = value.strip()
            normalized = keyword.casefold()
            if keyword and normalized not in seen:
                result.append(keyword)
                seen.add(normalized)
        return result
