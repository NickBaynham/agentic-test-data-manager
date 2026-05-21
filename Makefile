# Agentic Test Data Manager — top-level Makefile
# All targets are .PHONY. Each target prints what it is doing on its first line.
# LLM mode is OFF in the demo path. Never set ATDM_PLANNER=llm here.

.DEFAULT_GOAL := help

PDM ?= pdm
COMPOSE ?= docker compose -f infra/docker-compose.yml

.PHONY: help setup lint test test-unit test-integration build up down down-clean logs ps migrate demo smoke baseline-snapshot reset-baseline clean playwright-install playwright-test

help:
	@echo "Agentic Test Data Manager — Make targets"
	@echo ""
	@echo "  setup              Install Python deps via pdm."
	@echo "  lint               Run ruff and mypy --strict."
	@echo "  test               Run unit tests (no Docker). Alias for test-unit."
	@echo "  test-unit          Run unit tests per source root (no Docker required)."
	@echo "  test-integration   Run integration and e2e tests (brings up docker compose stack)."
	@echo "  build              Build all docker images defined in infra/docker-compose.yml."
	@echo "  up                 Bring up the local stack and wait for healthy (Postgres, MinIO, SUT, agent)."
	@echo "  down               Stop and remove the local stack containers (volumes preserved)."
	@echo "  down-clean         Stop, remove containers, AND DELETE VOLUMES (destructive)."
	@echo "  logs               Tail logs from the stack."
	@echo "  ps                 Show stack status."
	@echo "  migrate            Apply SQL migrations to the running Postgres (idempotent)."
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
	@echo "[lint] mypy --strict (test-data-agent app+tests)"
	$(PDM) run mypy --config-file mypy.ini apps/test-data-agent/app apps/test-data-agent/tests
	@echo "[lint] mypy --strict (atdm-client package)"
	$(PDM) run mypy --config-file mypy.ini apps/test-data-agent/python
	@echo "[lint] mypy --strict (target-healthcare-api)"
	$(PDM) run mypy --config-file mypy.ini apps/target-healthcare-api
	@echo "[lint] mypy --strict (tests)"
	$(PDM) run mypy --config-file mypy.ini tests

test: test-unit

test-unit:
	@echo "[test-unit] root tests (excluding integration / e2e)"
	$(PDM) run pytest tests -m "not integration and not e2e"
	@echo "[test-unit] target-healthcare-api"
	PYTHONPATH=apps/target-healthcare-api $(PDM) run pytest apps/target-healthcare-api/tests
	@echo "[test-unit] test-data-agent"
	PYTHONPATH=apps/test-data-agent $(PDM) run pytest apps/test-data-agent/tests
	@echo "[test-unit] atdm-client"
	PYTHONPATH=apps/test-data-agent/python $(PDM) run pytest apps/test-data-agent/python/tests

test-integration:
	@echo "[test-integration] stack integration / e2e tests (requires Docker, brings up stack)"
	$(PDM) run pytest tests -m "integration or e2e" -v

build:
	@echo "[build] docker compose build"
	$(COMPOSE) build

up:
	@echo "[up] docker compose up -d (stack will be ready when long-running services are healthy)"
	$(COMPOSE) up -d --wait

down:
	@echo "[down] docker compose down (volumes preserved)"
	$(COMPOSE) down

down-clean:
	@echo "[down-clean] docker compose down -v (REMOVES VOLUMES)"
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

migrate:
	@echo "[migrate] applying SQL migrations to running Postgres"
	@for f in apps/target-healthcare-api/migrations/*.sql; do \
		echo "  -> $$f"; \
		$(COMPOSE) exec -T postgres psql -U $${POSTGRES_USER:-atdm} -d $${POSTGRES_DB:-target_healthcare} -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/$$(basename $$f); \
	done

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

playwright-install:
	@echo "[playwright-install] one-time install of Node deps + Chromium"
	cd automation/playwright && npm install && npx playwright install chromium

playwright-test:
	@echo "[playwright-test] run example Playwright spec (requires FIXTURE_PATH)"
	@test -n "$$FIXTURE_PATH" || (echo "FIXTURE_PATH must point at a JSON fixture from 'atdm request ... --playwright'"; exit 2)
	cd automation/playwright && npx playwright test
