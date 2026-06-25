import requests
import json
import base64
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

CLIENT_ID = os.getenv("DIGIKEY_CLIENT_ID")
CLIENT_SECRET = os.getenv("DIGIKEY_CLIENT_SECRET")

TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
PRODUCT_URL = "https://api.digikey.com/products/v4/search/keyword"

# MPN = "STM32F103C8T6"
# MPN = "GCM155R71C104KA55"
MPN = "GCM155"


def get_access_token():
    auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {"grant_type": "client_credentials"}

    response = requests.post(TOKEN_URL, headers=headers, data=data)
    response.raise_for_status()

    return response.json()["access_token"]


def search_product(token, mpn):
    headers = {
        "Authorization": f"Bearer {token}",
        "X-DIGIKEY-Client-Id": CLIENT_ID,
        "Content-Type": "application/json",
    }

    payload = {"Keywords": mpn, "Limit": 10}

    response = requests.post(PRODUCT_URL, headers=headers, json=payload)
    response.raise_for_status()

    return response.json()


def extract_useful_fields(product):
    return {
        "mpn": product.get("ManufacturerProductNumber"),
        "manufacturer": product.get("Manufacturer", {}).get("Name"),
        "description": product.get("Description", {}).get("ProductDescription"),
        "datasheet": product.get("DatasheetUrl"),
        "category": product.get("Category", {}).get("Name"),
        "parameters": {
            p["ParameterText"]: p["ValueText"] for p in product.get("Parameters", [])
        },
    }


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("Missing DIGIKEY_CLIENT_ID or DIGIKEY_CLIENT_SECRET in .env")

    token = get_access_token()
    data = search_product(token, MPN)

    products = data.get("Products", [])
    if not products:
        print("No product found")
        return

    product = products

    print("=== RAW PRODUCT ===")
    # print(product)

    # print("\n=== EXTRACTED ===")
    # extracted = extract_useful_fields(product)
    # for k, v in extracted.items():
    #     print(f"{k}: {v}")

    json.dump(data, open(f"mau.json", "w"), indent=2)


if __name__ == "__main__":
    main()
