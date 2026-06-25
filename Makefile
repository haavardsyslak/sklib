.PHONY: all validate build clean next-id help web web-run install indexes

# Default target
all: validate build

# Install dependencies
install:
	@uv sync

# Validate all CSV files against the schema
validate:
	@python3 scripts/validate.py

# Build the SQLite database from CSV files
build:
	@python3 scripts/build_db.py

# Build KiCad library indexes (symbols and footprints)
indexes:
	@python3 scripts/build_indexes.py -v

# Clean generated files
clean:
	@rm -rf generated/*
	@echo "Cleaned generated files"

# Get next available ID for a category
# Usage: make next-id category=capacitors
next-id:
ifndef category
	@echo "Usage: make next-id category=<category>"
	@echo "Available categories:"
	@ls -1 src/parts/*.csv 2>/dev/null | xargs -I{} basename {} .csv | sed 's/^/  /'
else
	@python3 scripts/validate.py --next-id src/parts/$(category).csv
endif

# Run validation and build only if validation passes
check: validate build

# Web UI
web:
	@echo "Starting SKLib web UI..."
	@uv run uvicorn src.web.main:app --reload --port 8000 --host 127.0.0.1

# Run web UI without uv (requires dependencies installed)
web-run:
	@python3 -m uvicorn src.web.main:app --reload --port 8000 --host 127.0.0.1

# Help
help:
	@echo "SKLib - KiCad Parts Library"
	@echo ""
	@echo "Targets:"
	@echo "  make install       - Install dependencies with uv"
	@echo "  make indexes      - Build KiCad symbol/footprint indexes"
	@echo "  make validate     - Validate CSV files against schema"
	@echo "  make build        - Generate SQLite database"
	@echo "  make clean        - Remove generated files"
	@echo "  make next-id category=X - Get next ID for category"
	@echo "  make check        - Validate and build"
	@echo "  make web          - Start web UI (requires 'make install')"
	@echo "  make web-run      - Start web UI (requires dependencies)"
	@echo "  make help         - Show this help"
