# Power Position Tool

# Quick start:
#  	make run

# Verify:
#  	make setup
#  	make check

.DEFAULT_GOAL := help

.PHONY: help setup run demo _up stop logs run-local test lint typecheck check

PYTHON_PATH := src
DASHBOARD := src/app/dashboard/main.py

IMAGE := power-position
CONTAINER := power-position

# Override if 8501 is already taken on the host:  make run PORT=8600
PORT ?= 8501
URL := http://localhost:$(PORT)

# Extra `docker run` arguments, set per target below.
DOCKER_ARGS :=

# `make demo` mounts the config and data directories from the working copy over
# the ones baked into the image, so editing a YAML on the host is visible to the
# container. Without the mounts the image's own copies would win and a live
# config change would appear to do nothing.
DEMO_ARGS := \
	-e POWER_POSITION_TRADES_CSV=/app/src/app/data/demo_trades.csv \
	-v "$(CURDIR)/src/app/config:/app/src/app/config:ro" \
	-v "$(CURDIR)/src/app/data:/app/src/app/data:ro"

help: ## Show available commands.
	@echo "Power Position Tool"
	@echo ""
	@echo "Quick start:"
	@echo "  make run        Build and open the dashboard in a browser (Docker)"
	@echo "  make stop       Stop the dashboard"
	@echo ""
	@echo "Verification:"
	@echo "  make setup      Install locked dependencies"
	@echo "  make check      Run tests, linting, and type checking"
	@echo ""
	@echo "Individual commands:"
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk -F':.*?## ' '{printf "  %-16s %s\n", $$1, $$2}'

run: ## Build and start the dashboard in Docker, then open it in a browser.
run: _up

demo: ## Same, on the demo trade book, with config and data live-editable.
demo: DOCKER_ARGS := $(DEMO_ARGS)
demo: _up
	@echo ""
	@echo "    Demo mode. The trade book has deliberate bad rows, so the"
	@echo "    quarantine warning and the incomplete markers are visible."
	@echo ""
	@echo "    Edit src/app/config/, then press R in the browser to reload:"
	@echo "      areas.yaml        add '- Chubu'       -> D101 counts, Chubu appears"
	@echo "      trade_types.yaml  add '- OTC Options' -> D103 counts"
	@echo "      load_profiles.yaml add an Overnight block (see README) -> D102 counts"

_up:
	@docker version >/dev/null 2>&1 || { \
		echo "Docker does not look available or running."; \
		echo "  Start Docker Desktop and retry, or run without Docker:  make run-local"; \
		exit 1; \
	}
	@echo "==> Building $(IMAGE) (first run pulls the base image, so give it a minute)"
	@docker build -t $(IMAGE) .
	@docker rm -f $(CONTAINER) >/dev/null 2>&1 || true
	@echo "==> Starting the dashboard on port $(PORT)"
	@docker run -d --name $(CONTAINER) -p $(PORT):8501 $(DOCKER_ARGS) $(IMAGE) >/dev/null || { \
		echo "Could not start the container, usually because port $(PORT) is in use."; \
		echo "  Retry on another port:  make run PORT=8600"; \
		exit 1; \
	}
	@# Wait for Streamlit's own health endpoint to report ready, so the browser
	@# never opens on a server that is still booting. The container's
	@# HEALTHCHECK does the probing, which keeps this loop dependent only on
	@# docker rather than on curl being installed on the host.
	@printf "==> Waiting for the dashboard to come up"
	@waited=0; \
	while [ $$waited -lt 90 ]; do \
		state=$$(docker inspect -f '{{.State.Health.Status}}' $(CONTAINER) 2>/dev/null || echo unknown); \
		if [ "$$state" = "healthy" ]; then echo " ready"; break; fi; \
		running=$$(docker inspect -f '{{.State.Running}}' $(CONTAINER) 2>/dev/null || echo false); \
		if [ "$$running" != "true" ]; then \
			echo ""; \
			echo "The dashboard container exited before it was ready. Logs:"; \
			docker logs $(CONTAINER); \
			exit 1; \
		fi; \
		printf "."; \
		sleep 1; \
		waited=$$((waited + 1)); \
	done; \
	if [ $$waited -ge 90 ]; then \
		echo ""; \
		echo "Timed out waiting for the dashboard. Logs:"; \
		docker logs $(CONTAINER); \
		exit 1; \
	fi
	@echo "==> Dashboard ready at $(URL)"
	@if command -v open >/dev/null 2>&1; then open "$(URL)"; \
	elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$(URL)"; \
	else echo "    Open $(URL) in your browser."; fi
	@echo "    Stop it with:  make stop"

stop: ## Stop and remove the dashboard container.
	@# `docker rm -f` succeeds whether or not the container exists, so the
	@# message is driven by looking it up rather than by the exit status.
	@if [ -n "$$(docker ps -aq --filter name=^$(CONTAINER)$$ 2>/dev/null)" ]; then \
		docker rm -f $(CONTAINER) >/dev/null && echo "Dashboard stopped."; \
	else \
		echo "Dashboard was not running."; \
	fi

logs: ## Follow the dashboard container logs.
	docker logs -f $(CONTAINER)

run-local: ## Start the dashboard without Docker (needs uv and make setup).
	PYTHONPATH=$(PYTHON_PATH) uv run streamlit run $(DASHBOARD)

setup: ## Install the locked project dependencies.
	uv sync --frozen

test: ## Run the full pytest suite.
	PYTHONPATH=$(PYTHON_PATH) uv run pytest

lint: ## Run Ruff checks.
	PYTHONPATH=$(PYTHON_PATH) uv run ruff check src tests

typecheck: ## Run mypy.
	PYTHONPATH=$(PYTHON_PATH) uv run mypy

check: test lint typecheck ## Run all verification checks (tests, linting, and type checking).
