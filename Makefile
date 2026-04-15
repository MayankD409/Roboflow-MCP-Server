.PHONY: help sync dev test lint typecheck check inspector clean

help:
	@echo "Targets:"
	@echo "  sync       install dev dependencies via uv"
	@echo "  dev        run the MCP server over stdio"
	@echo "  test       run pytest with coverage"
	@echo "  lint       ruff format --check + ruff check"
	@echo "  typecheck  mypy"
	@echo "  check      lint + typecheck + test"
	@echo "  inspector  launch MCP Inspector against this server"
	@echo "  clean      remove caches and build artefacts"

sync:
	uv sync --all-extras

dev:
	uv run mcp-server-roboflow

test:
	uv run pytest --cov

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy src tests

check: lint typecheck test

inspector:
	npx --yes @modelcontextprotocol/inspector uv run mcp-server-roboflow

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage coverage.xml htmlcov dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
