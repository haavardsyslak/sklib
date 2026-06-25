import csv
from dataclasses import dataclass, field, fields
from pathlib import Path

from src.web.schema import get_columns, get_id_prefix


@dataclass
class Component:
    id: str
    component_type: str
    mpn: str
    manufacturer: str
    description: str
    symbol: str
    footprint: str
    lifecycle_status: str = "active"
    value: str = ""
    tolerance: str = ""
    package: str = ""
    rated_voltage: str = ""
    operating_temp: str = ""
    datasheet: str = ""
    supplier: str = ""
    supplier_sku: str = ""
    notes: str = ""
    keywords: str = ""
    exclude_from_bom: str = "0"
    extra_fields: dict = field(default_factory=dict)

    @classmethod
    def _dataclass_field_names(cls) -> set[str]:
        return {f.name for f in fields(cls) if f.name != "extra_fields"}

    @classmethod
    def from_row(cls, row: dict, inferred_type: str = "") -> "Component":
        attr_names = cls._dataclass_field_names()

        kwargs: dict[str, str] = {}
        for name in attr_names:
            if name == "component_type":
                kwargs[name] = row.get(name) or inferred_type
            elif name == "lifecycle_status":
                kwargs[name] = row.get(name, row.get("status", "active"))
            else:
                kwargs[name] = row.get(name, "")

        # Schema-defined columns not promoted to dataclass attrs, plus any
        # type-specific fields (e.g. capacitance), flow through extra_fields.
        extra = {
            k: v
            for k, v in row.items()
            if k not in attr_names and k != "status" and v and v.strip()
        }
        return cls(**kwargs, extra_fields=extra)

    def to_row(self) -> dict:
        row: dict[str, str] = {}
        for name in self._dataclass_field_names():
            row[name] = getattr(self, name, "")
        row.update(self.extra_fields)
        return row


_DEFAULT_PARTS_DIR = Path(__file__).parent.parent / "parts"


class CSVStore:
    def __init__(self, parts_dir: Path | None = None) -> None:
        self.parts_dir = parts_dir or _DEFAULT_PARTS_DIR
        self.parts_dir.mkdir(parents=True, exist_ok=True)

    def get_csv_path(self, component_type: str) -> Path:
        return self.parts_dir / f"{component_type}s.csv"

    def get_columns(self) -> list[str]:
        return list(get_columns().keys())

    def read_all(self, component_type: str) -> list[Component]:
        path = self.get_csv_path(component_type)
        if not path.exists():
            return []

        components = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("component_type", component_type) == component_type:
                    components.append(
                        Component.from_row(row, inferred_type=component_type)
                    )
        return components

    def read_all_types(self) -> dict[str, list[Component]]:
        result = {}
        for csv_file in self.parts_dir.glob("*.csv"):
            comp_type = csv_file.stem
            result[comp_type] = self.read_all(comp_type)
        return result

    def get_by_id(self, component_type: str, part_id: str) -> Component | None:
        components = self.read_all(component_type)
        for comp in components:
            if comp.id == part_id:
                return comp
        return None

    def get_next_id(self, component_type: str) -> str:
        components = self.read_all(component_type)
        prefix = get_id_prefix(component_type)
        max_num = 0
        for comp in components:
            if comp.id.startswith(prefix):
                try:
                    num = int(comp.id.split("-")[1])
                    max_num = max(max_num, num)
                except (ValueError, IndexError):
                    pass
        return f"{prefix}-{max_num + 1:04d}"

    def save(self, component: Component) -> None:
        path = self.get_csv_path(component.component_type)
        columns = self.get_columns()

        existing = self.read_all(component.component_type)

        extra_cols = set()
        for comp in existing:
            extra_cols.update(comp.extra_fields.keys())
        extra_cols.update(component.extra_fields.keys())
        all_columns = columns + sorted(extra_cols)

        updated = False
        for i, comp in enumerate(existing):
            if comp.id == component.id:
                existing[i] = component
                updated = True
                break

        if not updated:
            existing.append(component)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_columns, extrasaction="ignore")
            writer.writeheader()
            for comp in sorted(existing, key=lambda c: c.id):
                writer.writerow(comp.to_row())

    def delete(self, component_type: str, part_id: str) -> bool:
        components = self.read_all(component_type)
        original_len = len(components)
        components = [c for c in components if c.id != part_id]

        if len(components) == original_len:
            return False

        path = self.get_csv_path(component_type)
        if not components:
            path.unlink(missing_ok=True)
            return True

        columns = self.get_columns()
        extra_cols = set()
        for comp in components:
            extra_cols.update(comp.extra_fields.keys())
        all_columns = columns + sorted(extra_cols)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_columns, extrasaction="ignore")
            writer.writeheader()
            for comp in sorted(components, key=lambda c: c.id):
                writer.writerow(comp.to_row())

        return True

    def get_stats(self) -> dict:
        stats = {"total": 0, "by_type": {}}
        all_components = self.read_all_types()
        for comp_type, components in all_components.items():
            count = len(components)
            stats["total"] += count
            stats["by_type"][comp_type] = {
                "count": count,
                "label": comp_type.capitalize() + "s",
            }
        return stats
