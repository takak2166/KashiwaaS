.PHONY: setup install lint test

setup:
	@echo "Setting up development environment..."
	@command -v poetry >/dev/null 2>&1 || (echo "Installing Poetry..." && pip install poetry==2.3.2)
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