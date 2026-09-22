# Component data format

Each file contains one exact manufacturer part:

```text
parts/<component_type>/<ID>.toml
```

Example:

```toml
schema_version = 1
id = "CAP-7K3MP-9QWX2"
component_type = "capacitor"
mpn = "GRM155R71H104KE14D"
manufacturer = "Murata"
description = "MLCC 100nF 50V X7R 0402"
manufacturer_status = "active"
datasheet = "https://example.com/datasheet.pdf"
keywords = ["capacitor", "mlcc", "x7r"]
notes = "Stable general-purpose decoupling part."

[kicad]
symbol = "Device:C"
footprint = "Capacitor_SMD:C_0402_1005Metric"
exclude_from_bom = false

[specs]
capacitance = "100nF"
package = "0402"
tolerance = "10%"
rated_voltage = "50V"
dielectric = "X7R"

[[suppliers]]
name = "DigiKey"
sku = "490-1234-1-ND"
product_url = "https://www.digikey.com/example"
```

## Rules

- `schema_version` is currently `1`.
- New `id` values use the prefix from matching `types/*.toml` followed by two
  groups of five random Crockford Base32 characters, such as
  `CAP-7K3MP-9QWX2`.
- Legacy numeric IDs such as `CAP-0001` remain valid but are not generated.
- Random IDs use uppercase characters and omit ambiguous `I`, `L`, `O`, and
  `U`.
- Filename equals ID; parent directory equals component type.
- `manufacturer_status` is `active`, `not_recommended`, `obsolete`, or
  `unknown`.
- `symbol` and `footprint` use `Library:Name` syntax.
- `specs` accepts only fields declared by component type.
- Field names use lowercase `snake_case`.
- Datasheet and supplier URLs use HTTP or HTTPS.
- Volatile prices and stock levels are not committed.

Values with engineering units remain readable strings for now. Type definitions
may add stricter patterns later after conventions are tested with real parts.

The type definition's `value_field` selects the specification exported as
KiCad `Value`. It may instead be `mpn` for exact active parts. Canonical files
do not duplicate either value.
