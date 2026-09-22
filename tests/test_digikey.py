from sklib.suppliers.digikey import DigikeyMapper


def test_maps_passive_without_network() -> None:
    raw = {
        "ManufacturerProductNumber": "TEST-100",
        "Manufacturer": {"Name": "Example"},
        "Description": {"ProductDescription": "100nF capacitor"},
        "ProductStatus": {"Status": "Active"},
        "DatasheetUrl": "https://example.test/data.pdf",
        "ProductUrl": "https://example.test/product",
        "ProductVariations": [
            {
                "DigiKeyProductNumber": "123-ND",
                "PackageType": {"Name": "Cut Tape (CT)"},
                "QuantityAvailableforPackageType": 12345,
                "MinimumOrderQuantity": 1,
            }
        ],
        "Category": {"Name": "Capacitors"},
        "Parameters": [
            {"ParameterText": "Capacitance", "ValueText": "100 nF"},
            {"ParameterText": "Package / Case", "ValueText": "0402"},
            {"ParameterText": "Temperature Coefficient", "ValueText": "X7R"},
        ],
    }

    product = DigikeyMapper().map_product(raw)

    assert product.component_type == "capacitor"
    assert product.mpn == "TEST-100"
    assert product.manufacturer_status == "active"
    assert product.supplier_sku == "123-ND"
    assert product.stock_quantity == 12345
    assert product.minimum_order_quantity == 1
    assert product.packaging == "Cut Tape (CT)"
    assert product.specs == {
        "package": "0402",
        "capacitance": "100 nF",
        "dielectric": "X7R",
    }


def test_unknown_category_is_not_guessed() -> None:
    raw = {
        "ManufacturerProductNumber": "TEST-100",
        "Category": {"Name": "Unknown category"},
    }

    product = DigikeyMapper().map_product(raw)

    assert product.component_type == ""
