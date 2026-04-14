.PHONY: setup install lint test e2e-smoke

setup:
	@echo "Setting up development environment..."
	@command -v poetry >/dev/null 2>&1 || (echo "Installing Poetry..." && pip install poetry==2.3.4)
	@echo "Installing dependencies..."
	poetry install

install:
	@echo "Installing dependencies..."
	poetry install

lint:
	@echo "Running ruff format..."
	poetry run ruff format .
	@echo "Running ruff check..."
	poetry run ruff check . --fix

test:
	@echo "Running pytest..."
	poetry run pytest

e2e-smoke:
	@echo "Running Docker Compose E2E smoke (see docs/e2e.md)..."
	bash scripts/e2e_compose_smoke.sh