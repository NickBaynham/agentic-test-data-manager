# Development Guide

This guide is for engineers working **on** ATDM. End-user docs are in the
top-level [README.md](../README.md).

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.12 |
| pdm | 2.26+ |
| Docker Engine | 24+ |
| Docker Compose | v2 (`docker compose ...`, not legacy `docker-compose`) |
| GNU Make | any |

Verify with:

```bash
python3.12 --version
pdm --version
docker --version
docker compose version
```

## First-time setup

```bash
git clone git@github.com:NickBaynham/agentic-test-data-manager.git
cd agentic-test-data-manager
make setup       # pdm install
cp .env.example .env.local   # then edit if you want non-default secrets
```

## Day-to-day workflow

```bash
# Bring up the local stack (Postgres, MinIO, Target SUT stub, ATDM agent stub)
make up

# See what's running
make ps

# Tail container logs
make logs

# Run unit tests (no Docker)
make test          # or: make test-unit

# Run integration + e2e tests (uses the running stack)
make test-integration

# Lint and type-check
make lint

# Tear down (volumes preserved)
make down

# Tear down AND DELETE VOLUMES (destructive — wipes Postgres + MinIO data)
make down-clean
```

## Host port mapping

The stack uses **non-default host ports** to avoid colliding with other local
services. Container-internal ports are conventional; only the host side is
remapped. The full table lives in
[planning/PLAN.md Phase 1](../planning/PLAN.md#phase-1--docker-compose-postgres-minio-two-service-stubs).

| Service | Host port | URL |
|---|---|---|
| Postgres | `55432` | `postgres://atdm@localhost:55432/target_healthcare` |
| MinIO API | `19000` | `http://localhost:19000` |
| MinIO Console | `19001` | `http://localhost:19001` (browser; default creds in `.env.example`) |
| Target SUT | `18000` | `http://localhost:18000/health`, `http://localhost:18000/docs` |
| ATDM agent | `18001` | `http://localhost:18001/health`, `http://localhost:18001/metrics`, `http://localhost:18001/docs` |

Inside the compose network, services address each other by **service name +
container port** (e.g., `postgres:5432`, `minio:9000`). Host port mapping
only matters for connections from the developer's laptop.

## Project layout

```
apps/
  test-data-agent/
    app/              FastAPI agent — scenario requests, validators, seeders (Phase 3+)
    python/atdm/      Installable client library (Phase 7)
    tests/            Per-app unit tests
    requirements.txt  Container-side runtime deps
  target-healthcare-api/
    app/              FastAPI SUT — synthetic healthcare entities
    migrations/       SQL migrations (Phase 2)
    tests/            Per-app unit tests
    requirements.txt  Container-side runtime deps
automation/
  playwright/         Playwright tests (Phase 7)
  pytest-api/         pytest-API tests (Phase 7)
  fixtures/           Generated fixtures (gitignored)
data/
  catalogs/, parquet/, seed/   (Phase 3+; gitignored except .gitkeep)
docs/                 This guide and others
infra/
  docker-compose.yml  The local stack
planning/PLAN.md      Phase-by-phase build plan
requirements/         BRD, engineering handoff, original concept
scripts/              Operational scripts (e.g., cold-start benchmark)
tests/                Root-level tests; tests/integration is the stack suite
```

## Testing

Tests are split into three layers and **must be run separately per source root**
(see [PLAN.md Phase 0 Known pitfall](../planning/PLAN.md) — the duplicate-`app`
mypy/pytest trap).

| Layer | How to run | What it covers |
|---|---|---|
| **Unit (top-level)** | `pdm run pytest tests -m "not integration and not e2e"` | Repo-level utilities and architecture tests. |
| **Unit (per-app)** | `PYTHONPATH=apps/<name> pdm run pytest apps/<name>/tests` | FastAPI stubs and (later) generators, validators, seeders. |
| **Integration** | `make test-integration` | Tests that hit the running compose stack. Tagged `@pytest.mark.integration`. |
| **E2E** | `make test-integration` (subset by `-m e2e`) | Full make-up → assert → make-down cycles. Tagged `@pytest.mark.e2e`. |

`make test` runs only the unit layers — never Docker. CI keeps the same
separation: `lint` and `test` jobs are Docker-free; the `stack` job runs
`make up && make test-integration && make down`.

## Adding a new endpoint

1. Add the route to `apps/<name>/app/main.py` (Phase 1) — later it'll move
   to `apps/<name>/app/api/...` (Phase 3+).
2. Write the unit test under `apps/<name>/tests/test_<feature>.py` using
   `fastapi.testclient.TestClient`.
3. Run that app's tests:
   ```bash
   PYTHONPATH=apps/<name> pdm run pytest apps/<name>/tests
   ```
4. If the endpoint is observed from outside the stack, add an integration
   test under `tests/integration/`.
5. Run `make lint && make test && make test-integration` before commit.

## Cold-start benchmark (NFR-001)

To measure the stack cold-start budget (NFR-001: ≤ 60 seconds p95 over 5 runs):

```bash
./scripts/measure_cold_start.sh 5
```

Sample output on a reference Mac (M2, 16 GB):

```
  run 1: 18s
  run 2: 18s
  run 3: 18s
  run 4: 17s
  run 5: 17s
  p50 (median): 18s
  p95 (max):    18s
  NFR-001 budget: 60s p95
  status: PASS
```

If p95 exceeds 60s on your hardware, investigate before scaling up the stack.

## Troubleshooting

### `make up` fails with `bind: address already in use`

Another process is holding one of the host ports (`55432`, `19000`, `19001`,
`18000`, `18001`). Find it:

```bash
lsof -nP -iTCP:55432 -iTCP:19000 -iTCP:19001 -iTCP:18000 -iTCP:18001 -sTCP:LISTEN
```

If it's an old ATDM stack still running, `make down`. If it's something
unrelated, stop it or update the port mapping in
`infra/docker-compose.yml` (and the same table in PLAN.md, `.env.example`,
README, and this doc).

### Containers exit immediately after `make up`

Check logs:

```bash
make logs
# or for a single service:
docker logs atdm_test_data_agent
```

Common causes:
- `requirements.txt` install failed inside the container (network blip; retry `make up`).
- Code change in `app/main.py` has a syntax error — check the uvicorn log.

### Integration tests can't reach the stack

The session fixture (`tests/integration/conftest.py`) auto-detects whether the
stack is already up. If you want to debug a test against a long-running stack,
set:

```bash
export ATDM_KEEP_STACK_UP=1
make up
make test-integration
```

The fixture will skip tear-down, and the warm-start e2e test will skip.

### MinIO console is not loading at `http://localhost:19001`

Verify the container is healthy: `make ps`. Default credentials are in
`.env.example` (`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`).

### `make lint` fails with `Duplicate module named "app"`

You probably tried to lint or test across both `apps/` packages in a single
mypy/pytest invocation. The Makefile is set up to invoke per source root
specifically to avoid this. See
[PLAN.md Phase 0 Known pitfall](../planning/PLAN.md) for the full story.

## Conventions

- No emojis in source files, logs, or UI (per project [CLAUDE.md](../CLAUDE.md)).
- `pdm` only. No `pip install` outside container `requirements.txt` files.
- All shared system tools (Postgres, MinIO) run in Docker locally.
- Maintain `CHANGELOG.md`, `FEATURES.md`, `TODO.md` with every merged change.
- When you encounter a surprise, write the resolution into the appropriate
  doc (PLAN.md "Known pitfall", CHANGELOG "Lessons learned", or here) so the
  next replay doesn't burn time on it again.
