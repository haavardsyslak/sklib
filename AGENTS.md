# AGENTS.md - SKLib Development Guide

SKLib is a Git-friendly KiCad DBLib parts library. Stores atomic parts as CSV files and generates a SQLite database for KiCad 7.0+. Includes a FastAPI web UI.

## Project Structure
```
sklib/
├── src/
│   ├── parts/           # CSV part definitions (source of truth)
│   │   ├── capacitors.csv, resistors.csv, connectors.csv
│   ├── schema.json      # JSON Schema with component field definitions
│   └── web/            # Web UI (FastAPI + Jinja2)
│       ├── main.py     # FastAPI app entry point
│       ├── csv_store.py # CSV read/write operations
│       ├── schema.py   # Schema loading utilities
│       └── routes/     # API routes
├── scripts/
│   ├── build_db.py     # CSV → SQLite generator
│   └── validate.py     # Schema validation
├── generated/          # Build artifacts (gitignored)
│   └── sklib.db        # SQLite database for KiCad
├── Makefile
└── pyproject.toml
```

## Build/Lint/Test Commands

### Make Targets
```bash
make install      # Install dependencies with uv
make validate     # Validate CSV files against schema
make build        # Generate SQLite database from CSVs
make check        # Validate then build
make clean        # Remove generated files
make indexes      # Build KiCad symbol/footprint indexes
make next-id category=capacitors  # Get next available ID
make web          # Start web UI (http://127.0.0.1:8000)
```

### Direct Python Scripts
```bash
python scripts/validate.py src/parts/capacitors.csv
python scripts/validate.py --next-id src/parts/capacitors.csv
python scripts/build_db.py --output custom.db --no-dbl
```

### Linting/Formatting (ruff)
```bash
ruff check .      # Lint all Python files
ruff format .    # Format all Python files
ruff check src/web/main.py  # Lint single file
```

### Testing (pytest)
```bash
pytest                        # Run all tests
pytest tests/test_csv.py      # Run single test file
pytest -v                     # Verbose output
pytest -k "test_name"         # Run tests matching pattern
```

## Code Style Guidelines

### General
- Python 3.13+, **88 char line length**, **4 spaces** (no tabs)
- **Always use type hints** for function parameters and returns
- **No comments** unless explicitly required

### Imports (order: stdlib → third-party → local)
```python
import argparse
import csv
import json
import sys
from pathlib import Path
```

### Naming Conventions
| Type | Convention | Example |
|------|------------|---------|
| Functions/variables | `snake_case` | `load_schema`, `csv_path` |
| Constants | `SCREAMING_SNAKE_CASE` | `PARTS_DIR` |
| Classes | `PascalCase` | `Component`, `CSVStore` |
| Modules | `snake_case` | `csv_store.py` |

### Docstrings (Google-style)
```python
def validate_csv(csv_path: Path, schema: dict) -> tuple[list[str], list[str], int]:
    """
    Validate a CSV file against the schema.

    Args:
        csv_path: Path to the CSV file to validate
        schema: Loaded schema dictionary

    Returns:
        Tuple of (errors, warnings, row_count)
    """
```

### FastAPI Routes Pattern
```python
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def list_components(request: Request, component_type: str | None = None):
    env = request.app.state.jinja_env
    template = env.get_template("components/list.html")
    return template.render(request=request, components=components)
```

### File Operations
```python
with open(csv_path, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    if reader.fieldnames is None:  # Check for empty files
        return []
```
- Always use `encoding="utf-8"` and `newline=""`
- Use `Path` for all file paths

### Error Handling
```python
# Scripts: return 1 on error, 0 on success
if error:
    print(f"Error: {message}", file=sys.stderr)
    return 1

# File operations: wrap in try/except for user-facing errors
try:
    with open(path) as f:
        return json.load(f)
except Exception as e:
    errors.append(f"Failed to read file: {e}")
```

## CSV Data Format

### Base Columns
`id`, `component_type`, `mpn`, `manufacturer`, `description`, `symbol`, `footprint`, `lifecycle_status`

### ID Patterns
- Pattern: `^[A-Z]{2,4}-\d{4,}$` (e.g., `CAP-0001`, `RES-0042`)
- Status: `active`, `deprecated`, or `obsolete`
- Symbol/footprint: `Library:Name` format

### ID Prefixes
| Category | Prefix | Example |
|----------|--------|---------|
| capacitors | CAP | CAP-0001 |
| resistors | RES | RES-0001 |
| inductors | IND | IND-0001 |
| diodes | DIO | DIO-0001 |
| connectors | CON | CON-0001 |

## Key Files
- `src/schema/`: Schema definitions (split into multiple files)
  - `src/schema/base.json`: Column definitions, ID prefixes, common symbols/footprints
  - `src/schema/types/*.json`: Component type-specific fields
- `src/supplier/mappings/digikey.json`: DigiKey API field mappings
- `src/supplier/component_mapper.py`: Base mapper interface for supplier APIs
- `src/web/main.py`: FastAPI application
- `src/web/csv_store.py`: CSV read/write with `Component` dataclass
