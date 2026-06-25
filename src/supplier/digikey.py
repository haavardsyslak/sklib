import base64
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from dotenv import load_dotenv

from .component_mapper import SupplierMapper, load_supplier_mapping, MappedProduct

if TYPE_CHECKING:
    from .coverage import CoverageTracker


def _normalize_package(value: str) -> str:
    if not value or value == "-":
        return ""
    match = re.match(r"^(\d{4})(?:\s+\(.+\))?$", value)
    if match:
        return match.group(1)
    return value.strip()


def _normalize_tolerance(value: str) -> str:
    if not value or value == "-":
        return ""
    return value.replace("±", "").replace("%", "%").strip()


def _normalize_temp_range(value: str) -> str:
    if not value or value == "-":
        return ""
    result = value.replace("°", "").replace("~", ", ")
    return re.sub(r"\s+", " ", result).strip()


def _normalize_voltage(value: str) -> str:
    if not value or value == "-":
        return ""
    return value.strip()


def _normalize_value(value: str) -> str:
    pass


DIGIKEY_NORMALIZERS: dict[str, callable] = {
    "package": _normalize_package,
    "tolerance": _normalize_tolerance,
    "operating_temp": _normalize_temp_range,
    "rated_voltage": _normalize_voltage,
    "voltage_rating": _normalize_voltage,
}


class DigikeyMapper(SupplierMapper):
    supplier_name = "digikey"

    def __init__(self, tracker: "CoverageTracker | None" = None):
        mappings = load_supplier_mapping(self.supplier_name)
        super().__init__(mappings, DIGIKEY_NORMALIZERS, tracker)


class DigikeyInterface:
    def __init__(self, coverage: bool = False):
        load_dotenv()
        self._client_id = os.getenv("DIGIKEY_CLIENT_ID")
        self._client_secret = os.getenv("DIGIKEY_CLIENT_SECRET")
        self._token_url = "https://api.digikey.com/v1/oauth2/token"
        self._product_url = "https://api.digikey.com/products/v4/search/keyword"
        self._tracker: "CoverageTracker | None" = None
        if coverage:
            from .coverage import get_tracker

            self._tracker = get_tracker()
            self._mapper = DigikeyMapper(tracker=self._tracker)
        else:
            self._mapper = DigikeyMapper()
        self._token = self._get_access_token()

    def search_product(self, mpn: str) -> list[dict]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "X-DIGIKEY-Client-Id": self._client_id,
            "Content-Type": "application/json",
        }
        payload = {"Keywords": mpn, "Limit": 10}
        response = requests.post(self._product_url, headers=headers, json=payload)
        return response.json().get("Products", [])

    def search_and_map(self, mpn: str) -> list[MappedProduct]:
        raw_results = self.search_product(mpn)
        products = [self._mapper.parse_product(raw) for raw in raw_results]
        if self._tracker:
            for product in products:
                all_fields = self._mapper.get_expected_fields(
                    product.metadata.get("component_type", "")
                )
                product_fields = {
                    **product.base,
                    **product.general,
                    **product.procurement,
                    **product.parameters,
                }
                full_fields = {f: product_fields.get(f) for f in all_fields}
                self._tracker.record_product(
                    product.base.get("mpn", ""),
                    product.metadata.get("component_type", ""),
                    full_fields,
                )
            self._tracker.record_request(len(products))
        return products

    def _get_access_token(self) -> str:
        auth = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()

        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        data = {"grant_type": "client_credentials"}

        response = requests.post(self._token_url, headers=headers, data=data)
        response.raise_for_status()

        return response.json()["access_token"]


if __name__ == "__main__":
    import json
    import pprint

    sample_file = Path(__file__).parent.parent.parent.parent / "GCM155R71C104KA55J.json"
    if sample_file.exists():
        with open(sample_file) as f:
            raw = json.load(f)
        mapper = DigikeyMapper()
        product = mapper.parse_product(raw)
        pprint.pprint(product.to_dict())
