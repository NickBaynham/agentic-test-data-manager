# Agentic Test Data Manager — top-level Makefile
# All targets are .PHONY. Each target prints what it is doing on its first line.
# LLM mode is OFF in the demo path. Never set ATDM_PLANNER=llm here.

.DEFAULT_GOAL := help

PDM ?= pdm
COMPOSE ?= docker compose -f infra/docker-compose.yml

.PHONY: help setup lint test build up down demo smoke baseline-snapshot reset-baseline clean

help:
	@echo "Agentic Test Data Manager — Make targets"
	@echo ""
	@echo "  setup              Install Python deps via pdm."
	@echo "  lint               Run ruff and mypy --strict."
	@echo "  test               Run pytest with coverage."
	@echo "  build              Build all docker images defined in infra/docker-compose.yml."
	@echo "  up                 Bring up the local stack (Postgres, MinIO, Target SUT, ATDM agent)."
	@echo "  down               Stop and remove the local stack containers (volumes preserved)."
	@echo "  demo               Run the end-to-end intent-to-data demo. Phase 9 deliverable."
	@echo "  smoke              Quick round-trip smoke test exercising all five reset strategies."
	@echo "  baseline-snapshot  Capture the Target SUT current state as a baseline."
	@echo "  reset-baseline     Restore the Target SUT to the most recent baseline."
	@echo "  clean              Remove caches and coverage artifacts."

setup:
	@echo "[setup] installing python deps via pdm"
	$(PDM) install

lint:
	@echo "[lint] ruff check"
	$(PDM) run ruff check .
	@echo "[lint] ruff format --check"
	$(PDM) run ruff format --check .
	@echo "[lint] mypy --strict (test-data-agent)"
	$(PDM) run mypy --config-file mypy.ini apps/test-data-agent
	@echo "[lint] mypy --strict (target-healthcare-api)"
	$(PDM) run mypy --config-file mypy.ini apps/target-healthcare-api
	@echo "[lint] mypy --strict (tests)"
	$(PDM) run mypy --config-file mypy.ini tests

test:
	@echo "[test] pytest"
	$(PDM) run pytest

build:
	@echo "[build] docker compose build (Phase 1+ — currently no images defined)"
	@if [ -f infra/docker-compose.yml ]; then $(COMPOSE) build; else echo "[build] infra/docker-compose.yml not present yet — skipping."; fi

up:
	@echo "[up] docker compose up -d (Phase 1+)"
	@if [ -f infra/docker-compose.yml ]; then $(COMPOSE) up -d; else echo "[up] infra/docker-compose.yml not present yet — Phase 1 work item."; fi

down:
	@echo "[down] docker compose down (Phase 1+)"
	@if [ -f infra/docker-compose.yml ]; then $(COMPOSE) down; else echo "[down] infra/docker-compose.yml not present yet — Phase 1 work item."; fi

demo:
	@echo "[demo] end-to-end intent-to-data demo (Phase 9 deliverable — not yet implemented)"
	@false

smoke:
	@echo "[smoke] reset-strategy round-trip (Phase 5+ deliverable — not yet implemented)"
	@false

baseline-snapshot:
	@echo "[baseline-snapshot] capture baseline (Phase 5+ deliverable — not yet implemented)"
	@false

reset-baseline:
	@echo "[reset-baseline] restore baseline (Phase 5+ deliverable — not yet implemented)"
	@false

clean:
	@echo "[clean] removing caches and coverage artifacts"
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build
	find . -type d -name __pycache__ -not -path './.venv/*' -not -path './__pypackages__/*' -exec rm -rf {} +
