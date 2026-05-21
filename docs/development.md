# Development Guide

This guide is for engineers working **on** ATDM. End-user docs are in the
top-level [README.md](../README.md).

## Prerequisites

### Required to run the stack and the demo

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

### Required only for the docs-generation workflow

| Tool | Version | Used by |
|---|---|---|
| Node.js | 20+ | the example Playwright test under `automation/playwright/` and the `make audit-screenshot` PNG capture |
| asciinema | latest | `make demo-cast` — captures `docs/assets/demo.cast` for the README. Without it, the demo still runs; you just can't regenerate the recording. |

Install on macOS:

```bash
brew install node asciinema
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

## Database schema and migrations

The Target SUT schema lives in `apps/target-healthcare-api/migrations/`. Files
are `NNNN_<description>.sql` in sequence — `0001_init.sql` lands the seven
entities and the baseline reference data (procedure / diagnosis codes).

### How migrations are applied

- **On a fresh Postgres volume:** the compose file bind-mounts `migrations/`
  into `/docker-entrypoint-initdb.d/` on the postgres container. Files in
  that directory are executed **once** when the data directory is first
  initialized.
- **On an existing volume:** `make migrate` runs every `.sql` file in the
  directory against the running Postgres via `psql`. The Phase 2 migration
  uses `CREATE TABLE IF NOT EXISTS` and `INSERT ... ON CONFLICT DO NOTHING`
  so it is idempotent — re-applying does nothing.
- **After schema changes (during dev):** the simplest path is
  `make down-clean && make up`. This wipes the Postgres volume so the
  entrypoint re-runs from scratch. `make down-clean` is destructive — only
  run it when you intend to throw away local data.

### Schema overview (Phase 2)

Seven entities per [BRD §9](../requirements/BRD.md):

- `plan`, `provider`, `member`, `eligibility`, `claim` — mutable, every row
  carries `test_run_id NOT NULL` with an index (DR-001 — required for the
  `reset_run` strategy in Phase 5).
- `procedure_code`, `diagnosis_code` — reference tables; `test_run_id` is
  nullable so baseline rows (shared across all runs) coexist with per-run
  "invalid" codes that drive denial scenarios.

NFR-010 markers are enforced at two levels:

- **Pydantic models** (fast feedback, returns 422 before DB round-trip).
- **DB CHECK constraints** (defense in depth, catches inserts that bypass
  the agent): `member.first_name`/`last_name` must start with `FAKE_`;
  `member.address_state` must equal `ZZ`.

### Inspecting the schema

```bash
docker exec atdm_postgres psql -U atdm -d target_healthcare -c "\dt"
docker exec atdm_postgres psql -U atdm -d target_healthcare -c "\d+ member"
```

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

## Intent-to-data request (Phase 3 — headline endpoint)

The ATDM agent now serves the headline endpoint. End-to-end example against
the local stack:

```bash
# Request a scenario. The Authorization header is required for all mutations.
RESP=$(curl -fsS -X POST http://localhost:18001/test-data/requests \
  -H 'authorization: Bearer dev-token-change-me' \
  -H 'content-type: application/json' \
  -d '{"domain":"healthcare","scenario":"active_member_clean","constraints":{},
       "delivery":{"seed_target":true}}')
echo "$RESP" | jq .

RUN=$(echo "$RESP" | jq -r .test_run_id)
TOKEN=$(echo "$RESP" | jq -r .cleanup.cleanup_token)

# Inspect the audit trail.
curl -fsS "http://localhost:18001/audit/runs/$RUN" | jq '.events[].action'

# Reset.
curl -fsS -X POST "http://localhost:18001/test-data/runs/$RUN/reset" \
  -H 'authorization: Bearer dev-token-change-me' \
  -H 'content-type: application/json' \
  -d "{\"cleanup_token\":\"$TOKEN\"}" | jq .
```

### Adding a new scenario

1. Drop a YAML file in `apps/test-data-agent/app/scenarios/`. Required keys:
   `scenario_id`, `generators` (ordered list of generator function names),
   `validators` (list of dotted validator names), `linked_requirement_ids`
   (FR-044; may be empty but the field is mandatory).
   Optional: `default_constraints` (a dict merged BEFORE the caller's
   constraints, so callers can override).
2. If the scenario needs new generators, add them under
   `apps/test-data-agent/app/generators/` and register them in the seeder's
   `_GENERATORS` map.
3. The scenario registry loads at agent startup — `docker compose restart
   test-data-agent` for changes to take effect.

### Available scenarios (Phase 4)

| scenario_id | What it builds |
|---|---|
| `active_member_clean` | Active member, in-network provider, paid claim within window. |
| `claim_denial_active_member` | Active member, out-of-network provider, denied claim with invalid procedure code. Exercises all 4 validators. |
| `expired_eligibility` | Member with eligibility window that ended last year; recent claim denied. |
| `out_of_network_pending_claim` | Active member, out-of-network provider, claim pending review. |
| `inactive_member_with_history` | Inactive member with historical paid claim (soft-delete semantics). |

### Audit UI (Phase 8)

Every scenario request produces a Parquet audit trail at
`s3://atdm-audit/runs/<run_id>.parquet`. Two read surfaces:

- **JSON**: `GET /audit/runs/<run_id>` — for programs.
- **HTML**: `GET /ui/audit/<run_id>` — for humans. Server-rendered (no
  JavaScript build step), styled with Pico.css from a CDN. Page is
  ≤ 100 KB.

Open in a browser after the demo:
```
open http://localhost:18001/ui/audit/<run_id>
```

The page shows: a banner with run_id/invoker/status, the planner steps,
each validator's decision, the records created, fixtures emitted (paths),
the reset status badge, and a chronological event timeline.

A worked example of the underlying JSON (plus the rejected-plan variant
and a Phase 2 LLM placeholder) lives in
[design-decisions.md](design-decisions.md#worked-example-a-complete-audit-trail-rule-based-planner).

### Architecture fitness tests (Phase 8 — gates CI)

Three tests live under `tests/architecture/`:

| Test | Asserts |
|---|---|
| `test_no_sql_from_agents.py` | AR-003 — agent code never imports psycopg / asyncpg / sqlalchemy / sqlmodel, and never contains SQL-shaped literals. |
| `test_audit_log_append_only.py` | NFR-011 — no DELETE/PUT/PATCH route under `/audit/*`, no `delete_event` / `update_event` style functions. |
| `test_no_emoji.py` | NFR-012 — no emoji code points in any committed source / Markdown / YAML / TOML / HTML / TypeScript file. |

Run locally via `make test` (architecture suite is part of `test-unit`).
The CI `architecture` job fails the build on any violation.

### Audit metrics (Phase 8)

`GET /metrics` emits Prometheus text exposition including:

- `atdm_up{}` — the heartbeat (Phase 1).
- `atdm_audit_events_total{action, status}` — one increment per audit append.
- `atdm_audit_write_latency_seconds{}` — histogram per audit append.
- `atdm_audit_dropped_events_total` — must remain 0; non-zero means an
  audit write failed durability and the integration test fails.

### CLI and pytest plugin (Phase 7)

The `atdm` CLI is installed automatically via the editable `atdm-client`
package. The `atdm.pytest` plugin auto-loads via the pytest11 entry point.

```bash
# List loaded scenarios
atdm scenarios

# Request a scenario (constraints repeatable)
atdm request claim_denial_active_member \
  -c provider_network=out_of_network -c claim_status=denied

# Look up the audit trail by run_id
atdm audit 01KS3J3H4D4AFCQD98SEPJCPBP

# Reset a specific run
atdm reset 01KS3J3H4D4AFCQD98SEPJCPBP --token <cleanup_token>

# Baseline snapshot / restore / list
atdm baseline-snapshot --baseline-id golden-2026-05-20
atdm baseline-restore --baseline-id golden-2026-05-20
atdm baseline-list

# Destructive — clear every test_run_id-tagged row across all tables
atdm reset-all --confirm

# All commands take a global --output/-o (human | json)
atdm -o json scenarios | jq '.scenarios[].scenario_id'
```

The CLI reads `ATDM_API_URL` and `ATDM_API_TOKEN` from the environment.

### Using `@atdm_scenario` in pytest

```python
from atdm.pytest import atdm_scenario

@atdm_scenario("active_member_clean")
def test_member(atdm_data):
    # Data is seeded BEFORE this runs.
    assert atdm_data["data"]["member_id"].startswith("m-")
    # No cleanup needed — the fixture's teardown calls /reset for you.

@atdm_scenario("claim_denial_active_member", constraints={"provider_network": "out_of_network"})
def test_denied_claim(atdm_data):
    assert atdm_data["data"]["claim_id"].startswith("claim-")
```

Or use `AtdmClient` directly:

```python
from atdm.client import AtdmClient

client = AtdmClient()
response = client.request_scenario("active_member_clean")
try:
    ...
finally:
    client.reset_run(response["test_run_id"], response["cleanup"]["cleanup_token"])
```

### Example Playwright test

```bash
# One-time
make playwright-install

# Generate a fixture, then run Playwright against it
atdm request active_member_clean --playwright
# (note the file path in the response; assume active_member_clean_<RUN>.json)
FIXTURE_PATH=automation/fixtures/active_member_clean_<RUN>.json make playwright-test
```

### Fixture delivery (Phase 6)

A scenario request can optionally emit a Playwright JSON fixture and/or a
pytest Python module fixture for the test runner to consume.

```bash
curl -fsS -X POST http://localhost:18001/test-data/requests \
  -H 'authorization: Bearer dev-token-change-me' \
  -H 'content-type: application/json' \
  -d '{"scenario":"claim_denial_active_member",
       "delivery":{"return_playwright_fixture":true,"return_pytest_fixture":true}}'
```

The response's `fixtures.playwright` and `fixtures.pytest` carry the absolute
container-side paths. On the host, the files appear under
`automation/fixtures/<scenario>_<run_id>.{json,py}` via the bind-mount.

- **Playwright JSON shape**: `{scenario_id, test_run_id, data, cleanup}`.
  A Playwright test can `JSON.parse(fs.readFileSync(...))` and use the keys
  directly.
- **pytest module**: exposes `SCENARIO_ID`, `TEST_RUN_ID`, and a
  `scenario_data() -> dict` function. Import via `importlib.util` from a
  pytest test, or (Phase 7) use the `atdm.pytest` decorator.

Fixture writes emit a `fixtures_emitted` audit event with the paths written.

### Reset strategies (Phase 5)

Five strategies, each demoable from the ATDM agent's HTTP API.

| Strategy | Endpoint | When to use |
|---|---|---|
| `reset_run` | `POST /test-data/runs/{run_id}/reset` | Per-scenario cleanup. Token-gated. Atomic FK-safe delete of just one run's records. |
| `reset_all` | `POST /test-data/reset/all` | Wipe every test_run_id-tagged row. Requires `X-Confirm: yes` header. Baseline reference rows preserved. |
| `baseline_snapshot` | `POST /test-data/baseline/snapshot` | Capture the current state of every mutable + reference table to Parquet in MinIO. Body optionally names the baseline. |
| `baseline_restore` | `POST /test-data/baseline/restore` | TRUNCATE everything and replay a named baseline (or the latest). Idempotent — re-running yields the same state. |
| `idempotent_seed` | — | Property of `baseline_restore`, not an endpoint. |

```bash
# Snapshot the current state
curl -fsS -X POST http://localhost:18001/test-data/baseline/snapshot \
  -H 'authorization: Bearer dev-token-change-me' \
  -H 'content-type: application/json' \
  -d '{"baseline_id":"golden-2026-05-20"}'

# List baselines
curl -fsS http://localhost:18001/test-data/baseline/list | jq .

# Restore (latest if baseline_id omitted)
curl -fsS -X POST http://localhost:18001/test-data/baseline/restore \
  -H 'authorization: Bearer dev-token-change-me' \
  -H 'content-type: application/json' \
  -d '{"baseline_id":"golden-2026-05-20"}'

# Nuke every test run (preserves reference data)
curl -fsS -X POST http://localhost:18001/test-data/reset/all \
  -H 'authorization: Bearer dev-token-change-me' \
  -H 'X-Confirm: yes'
```

Each strategy invocation emits its own audit trail under a synthetic
`strategy-{name}-{ULID}` run_id, with `*_started`, `*_completed`, and
on failure `*_failed` events. Look it up via
`GET /audit/runs/strategy-...`.

### Validators (Phase 4)

| Name | Rule |
|---|---|
| `relational.eligibility_status_matches_member` | inactive member ⇒ eligibility can't be active. |
| `relational.claim_references_existing_member` | claim.member_id must match bundle's member.member_id. |
| `domain.denial_requires_invalid_code` | denied claim must reference an invalid code OR carry a denial_reason. |
| `temporal.eligibility_window_contains_claim` | denied/pending claims must fall within eligibility window unless eligibility is expired. |

### Planner modes

- `ATDM_PLANNER=rule` (default in MVP) — deterministic lookup by scenario_id.
- `ATDM_PLANNER=llm` — Phase 4+; returns 501 `LLM_MODE_NOT_ENABLED` in MVP.

### Catalog and audit storage

The catalog (`s3://atdm-catalog/runs/{run_id}.parquet`) holds one row per
ScenarioRequest with the sha256 hash of its cleanup token. The audit log
(`s3://atdm-audit/runs/{run_id}.parquet`) holds the chronological event trail
for that run. Both live in MinIO — browse them at
`http://localhost:19001` (default creds in `.env.example`).

## Member entity (Phase 2 — internal use)

The Target SUT exposes Member CRUD under `/internal/`. These routes are
consumed by the agent's seeder (Phase 3+), not by humans, but they're
documented here for visibility.

```bash
# Create a plan first (Member.plan_id is a FK)
docker exec atdm_postgres psql -U atdm -d target_healthcare -c \
  "INSERT INTO plan VALUES ('plan-dev', 'Dev Plan', 'hmo', '2026-01-01', 'dev-run');"

# Create a member via the internal route
curl -fsS -X POST http://localhost:18000/internal/members \
  -H 'content-type: application/json' \
  -d '{"member_id":"m-dev","status":"active","first_name":"FAKE_Alice",
       "last_name":"FAKE_Smith","date_of_birth":"1990-04-12",
       "address":{"line1":"1 FAKE_Way","city":"FAKE_Town","state":"ZZ","zip":"00000"},
       "plan_id":"plan-dev","test_run_id":"dev-run"}'

# Count and delete
docker exec atdm_postgres psql -U atdm -d target_healthcare -tA -c \
  "SELECT COUNT(*) FROM member WHERE test_run_id='dev-run';"
curl -fsS -X DELETE "http://localhost:18000/internal/members?run_id=dev-run"
```

Browse the full OpenAPI doc at `http://localhost:18000/docs`.

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

### Tables are missing or schema looks wrong after schema changes

Postgres's `docker-entrypoint-initdb.d/` runs **only** when the data directory
is empty. If you've already brought up the stack and then changed the
migration files, the changes won't apply. Two ways forward:

- `make down-clean && make up` — wipes the postgres volume and lets the
  entrypoint re-run from scratch. Destructive.
- `make migrate` — runs every `.sql` file against the live Postgres via
  `psql`. Works if the migration is idempotent (the Phase 2 one is).

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
