.PHONY: install lint test

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