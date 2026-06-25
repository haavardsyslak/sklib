import functools

from src.supplier import SchemaLoader


@functools.cache
def load_schema() -> dict:
    base = SchemaLoader.get_base()
    types = SchemaLoader.get_types()
    return {
        "columns": base["columns"],
        "id_prefixes": base["id_prefixes"],
        "common_symbols": base["common_symbols"],
        "common_footprints": base["common_footprints"],
        "component_types": types,
    }


def get_component_types() -> dict:
    return SchemaLoader.get_types()


def get_columns() -> dict:
    return SchemaLoader.get_columns()


def get_id_prefix(component_type: str) -> str:
    type_info = SchemaLoader.get_type_info(component_type)
    return type_info.get("prefix", "UNK")


def get_common_symbol(component_type: str) -> str | None:
    return SchemaLoader.get_common_symbols().get(component_type)


def get_common_footprints() -> dict:
    return SchemaLoader.get_common_footprints()


def get_footprint_for_package(component_type: str, package: str) -> str | None:
    footprints = get_common_footprints()
    if package in footprints:
        return footprints[package].get(component_type)
    return None
