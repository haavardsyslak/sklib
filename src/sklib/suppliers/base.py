import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SupplierOffer:
    """Availability for one supplier packaging option."""

    sku: str
    packaging: str
    stock_quantity: int | None
    minimum_order_quantity: int | None


@dataclass(frozen=True)
class ProductSuggestion:
    """Supplier result normalized for review by a user."""

    component_type: str
    mpn: str
    manufacturer: str
    description: str
    manufacturer_status: str
    datasheet: str
    supplier_name: str
    supplier_sku: str
    supplier_url: str
    raw_category: str
    packaging: str
    stock_quantity: int | None
    minimum_order_quantity: int | None
    specs: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SupplierMapper:
    """Map supplier response fields through declarative aliases."""

    def __init__(self, mapping_path: Path) -> None:
        with open(mapping_path, encoding="utf-8") as file:
            self.mapping = json.load(file)

    def map_product(self, raw: dict[str, Any]) -> ProductSuggestion:
        category = _nested(raw, "Category.Name")
        component_type = self.mapping.get("category_map", {}).get(category, "")
        base = {
            name: self.resolve(raw, aliases)
            for name, aliases in self.mapping.get("base", {}).items()
        }
        specs = {
            name: self.resolve(raw, aliases)
            for name, aliases in self.mapping.get("general", {}).items()
        }
        for name, aliases in (
            self.mapping.get("parameters", {}).get(component_type, {}).items()
        ):
            specs.setdefault(name, self.resolve(raw, aliases))
        specs = {name: value for name, value in specs.items() if value}

        status = self.mapping.get("lifecycle_map", {}).get(
            base.get("manufacturer_status", ""), "unknown"
        )
        offer = _first_offer(raw)
        return ProductSuggestion(
            component_type=component_type,
            mpn=base.get("mpn", ""),
            manufacturer=base.get("manufacturer", ""),
            description=base.get("description", ""),
            manufacturer_status=status,
            datasheet=self.resolve(raw, ["DatasheetUrl"]),
            supplier_name="DigiKey",
            supplier_sku=offer.sku,
            supplier_url=self.resolve(raw, ["ProductUrl"]),
            raw_category=category,
            packaging=offer.packaging,
            stock_quantity=offer.stock_quantity,
            minimum_order_quantity=offer.minimum_order_quantity,
            specs=specs,
        )

    def resolve(self, raw: dict[str, Any], aliases: list[str]) -> str:
        for alias in aliases:
            if alias.startswith("Parameters:"):
                parameter_name = alias.split(":", 1)[1]
                for parameter in raw.get("Parameters", []):
                    if parameter.get("ParameterText") == parameter_name:
                        value = parameter.get("ValueText")
                        if value and value != "-":
                            return str(value).strip()
                continue
            if "[*]." in alias:
                collection, key = alias.split("[*].", 1)
                for item in raw.get(collection, []):
                    value = _nested(item, key)
                    if value:
                        return value
                continue
            value = _nested(raw, alias)
            if value:
                return value
        return ""


def _first_offer(raw: dict[str, Any]) -> SupplierOffer:
    variations = raw.get("ProductVariations", [])
    variation = (
        variations[0]
        if isinstance(variations, list)
        and variations
        and isinstance(variations[0], dict)
        else {}
    )
    stock = _integer(variation.get("QuantityAvailableforPackageType"))
    if stock is None:
        stock = _integer(raw.get("QuantityAvailable"))
    return SupplierOffer(
        sku=_nested(variation, "DigiKeyProductNumber"),
        packaging=_nested(variation, "PackageType.Name"),
        stock_quantity=stock,
        minimum_order_quantity=_integer(variation.get("MinimumOrderQuantity")),
    )


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _nested(document: dict[str, Any], path: str) -> str:
    value: Any = document
    for key in path.split("."):
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    if value is None:
        return ""
    return str(value).strip()
