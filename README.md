# SKLib - KiCad Parts Library

A Git-friendly KiCad DBLib parts library with CSV source files and SQLite database generation.

## Overview

This library stores **atomic parts** - each entry corresponds to a fully specified manufacturer part number (MPN) with mapped symbols, footprints, and metadata. It reuses KiCad's standard symbol and footprint libraries.

## Project Structure

```
sklib/
├── src/
│   ├── parts/           # CSV part definitions (source of truth)
│   │   ├── capacitors.csv
│   │   └── resistors.csv
│   └── schema.json      # Validation schema
├── generated/           # Build artifacts (gitignored)
│   └── sklib.db         # SQLite database for KiCad
├── kicad/
│   └── sklib.kicad_dbl  # KiCad database library config
├── scripts/
│   ├── build_db.py      # CSV → SQLite generator
│   └── validate.py      # Schema validation
└── Makefile
```

## Requirements

- Python 3.10+
- KiCad 7.0+ (for DBLib support)
- SQLite3 ODBC driver

### Installing SQLite ODBC Driver

**Ubuntu/Debian:**
```bash
sudo apt install libsqliteodbc
```

**Fedora:**
```bash
sudo dnf install sqliteodbc
```

**macOS:**
```bash
brew install sqliteodbc
```

**Windows:**
Download from http://www.ch-werner.de/sqliteodbc/

## Quick Start

```bash
# Validate CSV files
make validate

# Build SQLite database
make build

# Or both in one step
make check
```

## KiCad Setup

1. Build the database: `make build`
2. In KiCad, go to **Preferences → Manage Symbol Libraries**
3. Click the **Database Libraries** tab
4. Add the library: browse to `kicad/sklib.kicad_dbl`
5. Parts will appear in the symbol chooser under "SKLib Parts"

> **Note:** The `.kicad_dbl` uses a relative path (`${KIPRJMOD}/../generated/sklib.db`). 
> For this to work, your KiCad project should be in a sibling directory to `sklib/`, 
> or adjust the path in `sklib.kicad_dbl`.

## Adding Parts

### 1. Find the next available ID

```bash
make next-id category=capacitors
# Output: CAP-0004
```

### 2. Edit the CSV file

Add a new row to `src/parts/capacitors.csv`:

```csv
CAP-0004,GRM188R71H103KA01D,Murata,MLCC 10nF 50V X7R 0603,10nF,0603,Device:C,Capacitor_SMD:C_0603_1608Metric,https://...,capacitor mlcc,active,0
```

### 3. Validate and build

```bash
make check
```

### 4. Commit changes

```bash
git add src/parts/capacitors.csv
git commit -m "Add 10nF 50V 0603 MLCC (GRM188R71H103KA01D)"
```

## CSV Schema

| Column | Required | Description |
|--------|----------|-------------|
| `id` | Yes | Unique ID (`PREFIX-NNNN` format) |
| `mpn` | Yes | Manufacturer Part Number |
| `manufacturer` | Yes | Manufacturer name |
| `description` | Yes | Human-readable description |
| `value` | No | Component value (e.g., 100nF, 10K) |
| `package` | No | Package size (e.g., 0402, 0603) |
| `symbol` | Yes | KiCad symbol (`Library:Symbol`) |
| `footprint` | Yes | KiCad footprint (`Library:Footprint`) |
| `datasheet` | No | URL to datasheet |
| `keywords` | No | Space-separated search terms |
| `status` | Yes | `active`, `deprecated`, or `obsolete` |
| `exclude_from_bom` | No | `0` (default) or `1` to exclude from BOM |

The `description` and `keywords` columns map to KiCad's built-in symbol properties, enabling search in the Symbol Chooser.

## ID Prefixes

| Category | Prefix | Example |
|----------|--------|---------|
| Capacitors | CAP | CAP-0001 |
| Resistors | RES | RES-0001 |
| Inductors | IND | IND-0001 |
| Diodes | DIO | DIO-0001 |
| Transistors | TRN | TRN-0001 |
| ICs (Analog) | ICA | ICA-0001 |
| ICs (Digital) | ICD | ICD-0001 |
| Connectors | CON | CON-0001 |
| Crystals | XTL | XTL-0001 |
| LEDs | LED | LED-0001 |

## Common Symbol/Footprint Mappings

### Capacitors
| Package | Footprint |
|---------|-----------|
| 0402 | `Capacitor_SMD:C_0402_1005Metric` |
| 0603 | `Capacitor_SMD:C_0603_1608Metric` |
| 0805 | `Capacitor_SMD:C_0805_2012Metric` |
| 1206 | `Capacitor_SMD:C_1206_3216Metric` |

Symbol: `Device:C` (or `Device:C_Polarized` for electrolytics)

### Resistors
| Package | Footprint |
|---------|-----------|
| 0402 | `Resistor_SMD:R_0402_1005Metric` |
| 0603 | `Resistor_SMD:R_0603_1608Metric` |
| 0805 | `Resistor_SMD:R_0805_2012Metric` |
| 1206 | `Resistor_SMD:R_1206_3216Metric` |

Symbol: `Device:R`

## Make Targets

| Command | Description |
|---------|-------------|
| `make validate` | Check CSV files against schema |
| `make build` | Generate SQLite database |
| `make clean` | Remove generated files |
| `make next-id category=X` | Get next available ID |
| `make check` | Validate and build |
| `make help` | Show available targets |

## Troubleshooting

### "Database not found" in KiCad
- Ensure you've run `make build`
- Check the path in `sklib.kicad_dbl` matches your setup

### "ODBC driver not found"
- Install the SQLite ODBC driver (see Requirements)
- On Linux, you may need to configure `/etc/odbcinst.ini`

### Validation errors
- Check the error message for file and line number
- Ensure symbol/footprint use `Library:Name` format
- Verify ID format matches `PREFIX-NNNN`
