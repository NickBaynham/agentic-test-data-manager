# Agentic Test Data Manager (ATDM)

> **Status:** In development — Phase 0 (repo scaffold).
> ![CI](https://github.com/nickbaynham/agentic-test-data-manager/actions/workflows/ci.yml/badge.svg)

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

## Quickstart (current state)

Phase 0 deliverables only — scaffold lints, types-checks, and runs a trivial test.

```bash
make setup    # pdm install
make lint     # ruff + mypy --strict
make test     # pytest
```

Phase 1 (Docker stack, `make up`) is not yet implemented.

### Host ports (Phase 1+)

To avoid collisions with other local stacks (Postgres on 5432, MinIO on 9000/9001 are commonly held by unrelated projects), this stack maps to non-default host ports. See [planning/PLAN.md Phase 1](planning/PLAN.md#phase-1--docker-compose-postgres-minio-two-service-stubs) for the full table.

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
