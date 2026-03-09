.PHONY: lint test

# Prefer poetry; fall back to rye run python -m when poetry is not installed
RUN := $(shell command -v poetry >/dev/null 2>&1 && echo "poetry run" || echo "rye run python -m")

lint:
	@echo "Running black..."
	$(RUN) black .
	@echo "Running isort..."
	$(RUN) isort .
	@echo "Running flake8..."
	$(RUN) flake8 .

test:
	@echo "Running pytest..."
	$(RUN) pytest