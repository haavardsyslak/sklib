import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .coverage import CoverageTracker


@dataclass
class MappedProduct:
    base: dict = field(default_factory=dict)
    general: dict = field(default_factory=dict)
    procurement: dict = field(default_factory=dict)
    parameters: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "base": self.base,
            "general": self.general,
            "procurement": self.procurement,
            "parameters": self.parameters,
            "metadata": self.metadata,
        }


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class SchemaLoader:
    _instance = None
    _base: dict | None = None
    _types: dict[str, dict] | None = None

    @classmethod
    def get_base(cls) -> dict:
        if cls._base is None:
            cls._base = _load_json(
                Path(__file__).parent.parent / "schema" / "base.json"
            )
        return cls._base

    @classmethod
    def get_types(cls) -> dict[str, dict]:
        if cls._types is None:
            types_dir = Path(__file__).parent.parent / "schema" / "types"
            cls._types = {}
            for fp in types_dir.glob("*.json"):
                data = _load_json(fp)
                cls._types[data["name"]] = data
        return cls._types

    @classmethod
    def get_columns(cls) -> dict:
        return cls.get_base()["columns"]

    @classmethod
    def get_id_prefixes(cls) -> dict:
        return cls.get_base()["id_prefixes"]

    @classmethod
    def get_common_symbols(cls) -> dict:
        return cls.get_base()["common_symbols"]

    @classmethod
    def get_common_footprints(cls) -> dict:
        return cls.get_base()["common_footprints"]

    @classmethod
    def get_type_info(cls, type_name: str) -> dict:
        return cls.get_types().get(type_name, {})

    @classmethod
    def get_all_field_names(cls) -> set[str]:
        cols = cls.get_columns()
        type_fields = set()
        for t in cls.get_types().values():
            for f in t.get("fields", []):
                type_fields.add(f["name"])
        return set(cols.keys()) | type_fields


class SupplierMapper(ABC):
    def __init__(
        self,
        mappings: dict[str, Any],
        normalizers: dict[str, callable] | None = None,
        tracker: "CoverageTracker | None" = None,
    ):
        self.mappings = mappings
        self.base_map = mappings.get("base", {})
        self.general_map = mappings.get("general", {})
        self.procurement_map = mappings.get("procurement", {})
        self.param_maps = mappings.get("parameters", {})
        self.lifecycle_map = mappings.get("lifecycle_map", {})
        self.category_map = mappings.get("category_map", {})
        self.normalizers = normalizers or {}
        self.tracker = tracker

    def resolve(
        self, aliases: list[str], raw: dict, default: str = "", field_name: str = ""
    ) -> str:
        matched_alias: str | None = None
        for alias in aliases:
            if alias.startswith("_literal:"):
                matched_alias = alias
                return alias.split(":", 1)[1]
            if alias.startswith("Parameters:"):
                param_name = alias.split(":", 1)[1]
                params = raw.get("Parameters", [])
                for p in params:
                    if p.get("ParameterText") == param_name:
                        val = p.get("ValueText", "")
                        if val and val != "-":
                            matched_alias = alias
                            return self._normalize(alias, val)
                continue
            if "[*]" in alias:
                base_key, rest = alias.split("[*].", 1)
                for item in raw.get(base_key, []):
                    val = item.get(rest, "")
                    if val:
                        matched_alias = alias
                        return self._normalize(alias, val)
                continue
            if "." in alias:
                keys = alias.split(".")
                val = raw
                for k in keys:
                    if isinstance(val, dict):
                        val = val.get(k)
                    else:
                        val = None
                    if val is None:
                        break
                if val and isinstance(val, str):
                    matched_alias = alias
                    return self._normalize(alias, val)
                continue
            val = raw.get(alias, "")
            if val:
                matched_alias = alias
                return self._normalize(alias, val)
        if self.tracker and field_name:
            self.tracker.record_miss(field_name)
        return default

    def _normalize(self, alias: str, value: str) -> str:
        if not value or value in ("-", ""):
            return ""
        field_name = self._alias_to_field(alias)
        if self.tracker and field_name:
            self.tracker.record_hit(field_name, alias)
        if field_name in self.normalizers:
            return self.normalizers[field_name](value)
        return value.strip()

    def _alias_to_field(self, alias: str) -> str:
        for section in [self.base_map, self.general_map, self.procurement_map]:
            for field_name, aliases in section.items():
                if alias in aliases:
                    return field_name
        for type_map in self.param_maps.values():
            for field_name, aliases in type_map.items():
                if alias in aliases:
                    return field_name
        return ""

    def parse_product(self, raw: dict) -> MappedProduct:
        component_type = self.detect_component_type(raw)
        return MappedProduct(
            base=self.extract_base(raw),
            general=self.extract_general(raw),
            procurement=self.extract_procurement(raw),
            parameters=self.extract_parameters(raw, component_type),
            metadata=self.extract_metadata(raw, component_type),
            raw=raw,
        )

    def extract_base(self, raw: dict) -> dict:
        result = {}
        for field_name, aliases in self.base_map.items():
            val = self.resolve(aliases, raw, field_name=field_name)
            if field_name == "lifecycle_status":
                val = self.lifecycle_map.get(val, "active")
            result[field_name] = val
        return result

    def extract_general(self, raw: dict) -> dict:
        result = {}
        for field_name, aliases in self.general_map.items():
            val = self.resolve(aliases, raw, field_name=field_name)
            result[field_name] = val
        return result

    def extract_procurement(self, raw: dict) -> dict:
        result = {}
        for field_name, aliases in self.procurement_map.items():
            val = self.resolve(aliases, raw, field_name=field_name)
            result[field_name] = val
        return result

    def extract_parameters(self, raw: dict, component_type: str) -> dict:
        result = {}
        type_map = self.param_maps.get(component_type, {})
        extracted_general = {k: v for k, v in self.extract_general(raw).items() if v}
        for field_name, aliases in type_map.items():
            if field_name in extracted_general:
                continue
            val = self.resolve(aliases, raw, field_name=field_name)
            if val:
                result[field_name] = val
        return result

    def extract_metadata(self, raw: dict, component_type: str) -> dict:
        return {
            "component_type": component_type,
            "raw_category": raw.get("Category", {}).get("Name", ""),
            "supplier_url": raw.get("ProductUrl", ""),
            "series": raw.get("Series", {}).get("Name", ""),
        }

    def detect_component_type(self, raw: dict) -> str:
        category = raw.get("Category", {}).get("Name", "")
        return self.category_map.get(category, "capacitor")

    def get_expected_fields(self, component_type: str) -> set[str]:
        general_fields = set(self.general_map.keys())
        type_fields = set(self.param_maps.get(component_type, {}).keys())
        return general_fields | type_fields


def load_supplier_mapping(supplier_name: str) -> dict:
    mapping_path = Path(__file__).parent / "mappings" / f"{supplier_name}.json"
    return _load_json(mapping_path)
