import base64
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from sklib.suppliers.base import ProductSuggestion, SupplierMapper


class SupplierConfigurationError(ValueError):
    """Raised when required supplier credentials are unavailable."""


class DigikeyMapper(SupplierMapper):
    """Map DigiKey Product Information API responses."""

    def __init__(self) -> None:
        super().__init__(Path(__file__).parent / "mappings" / "digikey.json")


class DigikeyClient:
    """Small DigiKey Product Information API client."""

    def __init__(self, workspace_root: Path | None = None) -> None:
        if workspace_root is not None:
            load_dotenv(workspace_root / ".env")
        self.client_id = os.environ.get("DIGIKEY_CLIENT_ID", "")
        self.client_secret = os.environ.get("DIGIKEY_CLIENT_SECRET", "")
        if not self.client_id or not self.client_secret:
            raise SupplierConfigurationError(
                "DigiKey search requires DIGIKEY_CLIENT_ID and DIGIKEY_CLIENT_SECRET"
            )
        self.mapper = DigikeyMapper()
        self.session = requests.Session()
        self.token = self._access_token()

    def search(self, query: str) -> list[ProductSuggestion]:
        response = self.session.post(
            "https://api.digikey.com/products/v4/search/keyword",
            headers={
                "Authorization": f"Bearer {self.token}",
                "X-DIGIKEY-Client-Id": self.client_id,
                "Content-Type": "application/json",
            },
            json={"Keywords": query, "Limit": 10},
            timeout=20,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return [
            self.mapper.map_product(product) for product in payload.get("Products", [])
        ]

    def _access_token(self) -> str:
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        response = self.session.post(
            "https://api.digikey.com/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=20,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("DigiKey token response did not contain access_token")
        return token
