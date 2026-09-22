default:
    @just --list

install:
    uv sync

web:
    uv run sklib web

catalog-check:
    uv run sklib check

build:
    uv run sklib build

index:
    uv run sklib index

test:
    uv run pytest

consumer-smoke:
    uv build
    uv run python scripts/smoke_workspace.py

lint:
    uv run ruff check .
    uv run ruff format --check .

check: lint test catalog-check build
