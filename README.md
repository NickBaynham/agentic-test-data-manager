# Agentic Test Data Manager (ATDM)

> **Status:** In development — Phase 3 (first end-to-end vertical slice landed).
> ![CI](https://github.com/NickBaynham/agentic-test-data-manager/actions/workflows/ci.yml/badge.svg)

A local-first Quality Intelligence component for test data provisioning. Automation engineers and AI testing agents request scenario-grounded synthetic test data by intent and receive a validated dataset, a Playwright / pytest fixture, and a cleanup contract that guarantees the test environment can be restored.

## What this proves (target portfolio outcomes)

- Safe agentic QA architecture (tool-bounded planner, deterministic validators, auditable invocations).
- Test data lifecycle competence (generate, seed, reset, restore).
- Reusable, idiomatic Python that meets `ruff` + `mypy --strict` and ≥ 80 % coverage on core modules.
- Quality Intelligence linkage — every scenario can name the requirements it exercises.

The full case is built up phase-by-phase in [planning/PLAN.md](planning/PLAN.md). The architecture, decisions, and acceptance criteria live in [requirements/](requirements/).

## Documentation

| Document | Purpose |
|---|---|
| [requirements/concept.md](requirements/concept.md) | Original product concept and stack recommendation. |
| [requirements/BRD.md](requirements/BRD.md) | Canonical Business Requirements Document (18 sections). |
| [requirements/engineering-handoff.md](requirements/engineering-handoff.md) | Engineering-ready breakdown (epics, stories, APIs, tests). |
| [planning/PLAN.md](planning/PLAN.md) | 10-phase MVP build plan. |
| [CHANGELOG.md](CHANGELOG.md) | Per-change history. |
| [FEATURES.md](FEATURES.md) | What ships in MVP. |
| [TODO.md](TODO.md) | Phase 2+ items not yet built. |
| [docs/development.md](docs/development.md) | Engineer's day-to-day guide. |

## Quickstart

```bash
# One-time setup
make setup                  # pdm install
cp .env.example .env.local  # optional — defaults are fine for local dev

# Bring up the local stack (Postgres, MinIO, Target SUT, ATDM agent)
make up

# Hit the health endpoints
curl -fsS http://localhost:18000/health    # Target SUT
curl -fsS http://localhost:18001/health    # ATDM agent
curl -fsS http://localhost:18001/metrics   # Prometheus text

# When you're done
make down
```

Open `http://localhost:18000/docs` or `http://localhost:18001/docs` in a browser for the auto-generated FastAPI Swagger UI. The MinIO console is at `http://localhost:19001` (credentials in `.env.example`).

### Request a scenario (the headline endpoint)

```bash
curl -fsS -X POST http://localhost:18001/test-data/requests \
  -H 'authorization: Bearer dev-token-change-me' \
  -H 'content-type: application/json' \
  -d '{"scenario":"active_member_clean"}'
```

You'll receive a response with `test_run_id`, the seeded `member_id` / `plan_id`, and a `cleanup_token`. Use that token to tear the run down via `POST /test-data/runs/{run_id}/reset`. See [docs/development.md](docs/development.md#intent-to-data-request-phase-3--headline-endpoint) for the end-to-end example.

What's implemented today: Phase 0 (repo scaffold + CI), Phase 1 (Docker Compose stack), Phase 2 (target schema + Member entity), Phase 3 (intent-to-data: scenario request → seed → audit → reset for one scenario). What's coming: more scenarios + validators (Phase 4), reset strategies (Phase 5), fixtures (Phase 6), CLI (Phase 7), audit HTML page (Phase 8). See [planning/PLAN.md](planning/PLAN.md) for the full phase plan.

### Host ports

The stack uses **non-default host ports** to avoid colliding with other local stacks. Full table and reasoning in [planning/PLAN.md Phase 1](planning/PLAN.md#phase-1--docker-compose-postgres-minio-two-service-stubs).

| Service | Host port |
|---|---|
| Postgres | `55432` |
| MinIO API | `19000` |
| MinIO Console | `19001` |
| Target SUT (FastAPI) | `18000` |
| ATDM agent (FastAPI) | `18001` |

## Security model (MVP)

- Mutating endpoints will require `Authorization: Bearer ${ATDM_API_TOKEN}`. Read endpoints are open on the local network. This is portfolio-grade, not production-grade. See [BRD §16 decision #3](requirements/BRD.md#16-open-questions--resolved-2026-05-19).

## Data ethics

- All generated data is synthetic and carries a `FAKE_` prefix on identifying free-text fields and a `ZZ` fictional state code. There is no PHI, no real NPI numbers, no real SSNs. See [BRD §9](requirements/BRD.md) and NFR-010.

## License

MIT — see [LICENSE](LICENSE).
