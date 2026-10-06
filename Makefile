# Power Position Tool 

# Quick start:
#  	make setup
#  	make run

# Verify: 
#  	make check

.DEFAULT_GOAL := help

.PHONY: help setup run test lint typecheck check

PYTHON_PATH := src
DASHBOARD := src/app/dashboard/app.py

help: ## Show available commands.
	@echo "Power Position Tool"
	@echo ""
	@echo "Quick start:"
	@echo "  make setup      Install locked dependencies"
	@echo "  make run        Start the Streamlit dashboard"
	@echo ""
	@echo "Verification:"
	@echo "  make check      Run tests, linting, and type checking"
	@echo ""
	@echo "Individual commands:"
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk -F':.*?## ' '{printf "  %-16s %s\n", $$1, $$2}'

setup: ## Install the locked project dependencies.
	uv sync

run: ## Start the Streamlit dashboard.
	PYTHONPATH=$(PYTHON_PATH) uv run streamlit run $(DASHBOARD)

test: ## Run the full pytest suite.
	PYTHONPATH=$(PYTHON_PATH)uv run pytest

lint: ## Run Ruff checks.
	PYTHONPATH=$(PYTHON_PATH) uv run ruff check src tests

typecheck: ## Run mypy.
	PYTHONPATH=$(PYTHON_PATH) uv run mypy

check: test lint typecheck ## Run all verification checks (tests, linting, and type checking).
