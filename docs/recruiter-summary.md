# Agentic Test Data Manager — Recruiter Summary

**One page. Plain language. What this project is and what it proves.**

## What it is

An AI-augmented test-data platform. An automation engineer or AI testing
agent asks for a scenario by name — "active member with one denied claim
from an out-of-network provider" — and gets back:

- A validated, FK-consistent set of records in a Postgres-backed System
  Under Test.
- A Playwright JSON fixture and a pytest Python module that test runners
  can consume directly.
- A one-time `cleanup_token` and a `POST /reset` endpoint that wipes the
  run cleanly when the test finishes.
- A full audit trail of every action the agent took, queryable as JSON or
  viewable in a server-rendered HTML page.

## What it proves

| Claim | Evidence |
|---|---|
| AI-enabled QA architecture, designed for safety, not theatre | Tool-bounded planner with deterministic validators between the agent's plan and any SQL. Architecture fitness tests gate CI; the agent literally cannot write SQL. |
| Test data lifecycle competence | Five reset strategies live: per-run cleanup-token, reset-all, baseline snapshot, baseline restore, idempotent re-restore. All atomic, all audited. |
| Integration of LLMs with deterministic tools | `ATDM_PLANNER=llm` is wired but stubbed (501) in MVP. The architecture is built so the LLM produces a structured plan, the validator gates it, and an audited deterministic seeder is the only writer. |
| API design for autonomous testing agents | `POST /test-data/requests` returns a contract — `request_id`, `test_run_id`, entity PKs, fixture paths, cleanup token. An agent can call this and proceed without knowing the schema. |
| Quality intelligence connected to real automation | Every scenario YAML carries `linked_requirement_ids[]`. Phase 3+ can join scenarios to requirements to surface coverage gaps. |

## Key technologies

| Layer | Stack |
|---|---|
| Application | Python 3.12, FastAPI, Pydantic v2, asyncpg |
| Datastore | Postgres 16, MinIO (S3-compatible), Parquet via PyArrow |
| Agent | Custom Python (LLM stub via a feature flag; rule-based by default) |
| Test consumption | pytest with the `atdm.pytest` plugin; Playwright TypeScript via JSON fixtures |
| UI | Server-rendered Jinja2 + Pico.css (no JavaScript build) |
| Containers | Docker Compose with five services, 512 MB memory limits per long-running service |
| Observability | Prometheus metrics, structured Parquet audit log |
| CI | GitHub Actions: lint + unit + architecture + stack-integration jobs |
| Quality bars | `ruff` + `mypy --strict`, ≥80% coverage on core modules, architectural fitness tests gate CI |

## Try the demo (90 seconds)

```bash
make setup
make up
make demo
```

The final output prints a URL — open it in a browser to see the audit trail
UI. Screenshot in [docs/assets/audit-trail.png](assets/audit-trail.png).
Full reviewer guide in [demo-script.md](demo-script.md).

## How to read this repo

| Question | Look here |
|---|---|
| What does it actually do? | [demo-script.md](demo-script.md) |
| Why these architectural calls? | [design-decisions.md](design-decisions.md) |
| Component diagram and data flow | [architecture.md](architecture.md) |
| The domain model | [healthcare-domain-model.md](healthcare-domain-model.md) |
| Day-to-day dev workflow | [development.md](development.md) |
| Original concept document | [../requirements/concept.md](../requirements/concept.md) |
| Business requirements | [../requirements/BRD.md](../requirements/BRD.md) |
| Phase-by-phase build plan | [../planning/PLAN.md](../planning/PLAN.md) |

## Status

MVP complete. Local-first, single-developer build. Phase 2 enhancements
(real LLM planner, MCP server, vector retrieval) are scoped in
[../requirements/BRD.md §18](../requirements/BRD.md) but not built yet.

The project is licensed MIT and is at:
**[github.com/NickBaynham/agentic-test-data-manager](https://github.com/NickBaynham/agentic-test-data-manager)**
