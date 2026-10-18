.PHONY: install test lint format docs verify

install:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

docs:
	./scripts/check-docs.sh

# The full gate. Run this before calling a change done.
verify: lint test docs
