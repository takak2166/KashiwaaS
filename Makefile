.PHONY: setup install lint test

setup:
	@echo "Setting up development environment..."
	@command -v poetry >/dev/null 2>&1 || (echo "Installing Poetry..." && pip install poetry)
	@echo "Installing dependencies..."
	poetry install

install:
	@echo "Installing dependencies..."
	poetry install

lint:
	@echo "Running black..."
	poetry run black .
	@echo "Running isort..."
	poetry run isort .
	@echo "Running flake8..."
	poetry run flake8 .

test:
	@echo "Running pytest..."
	poetry run pytest