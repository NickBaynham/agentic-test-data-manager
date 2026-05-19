# Business Requirements Analysis: Agentic Test Data Manager (ATDM)

> **Document type:** Business Requirements Document (BRD)
> **Status:** Draft v0.1 — first-pass analysis
> **Source concept:** [concept.md](./concept.md)
> **Companion docs:** [engineering-handoff.md](./engineering-handoff.md), [README.md](./README.md)
> **Date:** 2026-05-19
> **Analyst voice:** Requirements Analyst + Product Strategy Mode + Implementation Handoff Mode (both enabled)

---

## Pre-flight: restating the idea

Rather than launching into 18 sections cold, the analyst first reframes the idea, names the objective, names the users, and surfaces the ambiguities that matter most. The rest of the document is the structured first pass; the assumptions made to fill in the gaps are labeled inline.

### Restated in clearer business language

The Agentic Test Data Manager (ATDM) is a **local-first Quality Intelligence component for test data provisioning**. It lets an automation engineer or AI testing agent request **scenario-grounded synthetic test data by intent** — for example, "active member with one denied claim and one pending claim" — and receive back a deterministically validated dataset, a fixture file consumable by Playwright or pytest, and a cleanup contract that guarantees the test environment can be restored. The platform combines a deterministic generator/seeder/reset core with a tool-bounded LLM planner that turns natural-language intent into a structured scenario plan.

### Likely business objective

This is a **portfolio artifact**, not a commercial product. The primary objective is to demonstrate, in a single repository, that the author can:

- Design AI-enabled QA architecture with safe LLM integration.
- Build reusable test data lifecycle automation (generate, seed, reset, audit).
- Treat agents as workflow participants with guardrails, traceability, and human checkpoints.
- Connect Quality Intelligence concepts (Coverage Intelligence, Source-grounded recommendation, Auditable AI output) to real automation execution.

A secondary objective is **reusable internal IP**: the deterministic generator/seeder/reset core could plausibly be applied to other portfolio or client projects with little change.

### Likely users

- **Automation engineer (primary day-to-day user)** — wants a Playwright/pytest fixture for a specific scenario, fast, repeatable, no manual DB setup.
- **AI testing agent (primary programmatic user)** — calls the API or MCP tools to retrieve scenario data as part of a larger agent-assisted testing workflow.
- **QA architect / hiring manager (primary observer)** — reviews the demo, the README, the audit log, and the design decisions document. This audience's reaction is the success criterion for the portfolio objective.
- **The author, in future projects (secondary user)** — reuses the generator/seeder/reset core in other portfolio work.

### Five biggest ambiguities (will be answered as assumptions until confirmed)

1. **Real LLM vs. mocked planner.** The concept says "Rules + LLM optional." Is the MVP demo expected to call a real LLM (OpenAI/Anthropic/local Ollama), or can it ship with a rule-based planner and a clearly-labeled "LLM mode" toggle? *Assumed:* MVP ships with rule-based planner; LLM mode is a Phase 2 toggle.
2. **Single domain or both.** Concept lists Option A (e-commerce) and Option B (synthetic healthcare). *Assumed:* MVP picks **synthetic healthcare-style** (Option B) — better job-description alignment — but the domain layer is abstracted so e-commerce can be added without core changes.
3. **MCP server in scope for MVP.** Concept calls MCP "later." *Assumed:* MCP server is **Phase 2**. MVP exposes HTTP API + CLI + Python fixture library only.
4. **Web dashboard in scope.** Concept lists `apps/web-dashboard` but also lists it under Version 2. *Assumed:* MVP ships **Swagger UI + a single read-only HTML audit-log page**; no React dashboard.
5. **Authentication.** Concept says nothing. *Assumed:* MVP uses a **single shared API token in an env var** (`ATDM_API_TOKEN`) protecting mutating endpoints; read endpoints are open on the local network. This is portfolio-grade, not production-grade — called out explicitly as a non-functional limitation.

---

## 1. Executive Summary

The Agentic Test Data Manager is a local-first Quality Intelligence component that lets automation engineers and AI testing agents request **scenario-grounded synthetic test data by intent**, receive a deterministically validated dataset plus framework-native fixtures (Playwright, pytest), seed a target system under test, and reset that target by test-run ID or to a golden baseline. The strategic bet is that the **deterministic generator/validator/seeder/reset core wrapped by a tool-bounded LLM planner** — not the LLM itself — is the differentiating story. Everything the LLM does is auditable, source-grounded, and human-reviewable; everything that mutates state is deterministic and reversible.

**Strategic bet (Product Strategy Mode):** The differentiator is **reset/cleanup discipline + auditable agent invocations**, not synthetic data generation. Faker-style generation is commodity. Anyone can produce a random member record. Almost nobody bothers to give every record a `cleanup_token`, a `test_run_id`, and a per-run audit trail that a QA architect can click through. Lead with that.

---

## 2. Business Goals

| # | Goal | Measure | Audience |
|---|---|---|---|
| G1 | Demonstrate end-to-end intent-to-data flow in a single `docker compose up` demo. | Demo completes in ≤ 60 seconds from clean state to first fixture returned, with no manual steps. | QA architect / hiring manager |
| G2 | Prove safe LLM integration (tool-bounded, validated, auditable). | 100 % of agent-initiated state mutations are mediated by deterministic validators and recorded in the audit log with prompt, tools called, and reviewer decision. | QA architect / hiring manager |
| G3 | Prove test data lifecycle competence: generate, seed, reset, restore. | All five reset strategies (`reset_all`, `reset_run`, `snapshot_restore`, `idempotent_seed`, `cleanup_token`) are demonstrable from the CLI and the HTTP API. | QA architect / hiring manager |
| G4 | Produce reusable, idiomatic Python that a senior engineer would be willing to ship. | `make lint`, `make test`, `make build` all pass; test coverage of generator/validator/seeder modules ≥ 80 % line coverage; no `# type: ignore` without a comment. | Hiring manager reviewing code |
| G5 | Tell a portfolio-quality story. | README ≤ 400 lines, one architecture diagram, one demo script, one design-decisions document; CHANGELOG and FEATURES kept current. | QA architect / hiring manager |

---

## 3. Primary Users and Stakeholders

| Persona | Role | Primary need | How they touch ATDM |
|---|---|---|---|
| **Alex** — Automation Engineer | Day-to-day user | "Give me a fixture for X scenario without me hand-crafting SQL." | Calls HTTP API or imports the pytest/Playwright fixture library. |
| **Aida** — AI Testing Agent | Programmatic user | Same as Alex, but via a structured tool interface. | Calls HTTP API (MVP) or MCP tools (Phase 2). |
| **Quinn** — QA Architect / Hiring Manager | Observer / approver of the portfolio bet | Wants to see safe agentic design, repeatable demos, and audit trails. | Reads README, runs demo, inspects audit log endpoint. |
| **Nick** — Author / Maintainer | Owner | Reuses the generator/seeder/reset core in future projects. | Maintains the codebase. |
| **Reviewer-as-recruiter** | Observer | Just wants to know in 90 seconds whether this is real. | Skims README + watches demo GIF if one exists. |

---

## 4. Problem Statement

Test automation teams routinely waste time hand-crafting SQL seed scripts, debugging stale fixtures, and chasing test failures that turn out to be data drift rather than product defects. The pain is sharpest at the **intersection of scenario complexity and environment reset** — for example, producing a healthcare-style member with one denied claim, one pending claim, and a valid eligibility record, then cleaning it up cleanly after the test. Existing tooling tends to fall into two camps: (a) raw fake-data libraries (Faker, Mimesis) that produce records but no relational consistency, lineage, or cleanup contract; (b) full-blown TDM platforms (Delphix, Broadcom TDM) that require enterprise procurement and assume regulated data.

Neither camp serves the agent-assisted testing use case, in which an LLM-driven test agent must request scenario-specific data through a structured, audited interface. ATDM occupies that gap: scenario-grounded, validated, seeded, traced, and reversible test data, designed from the start for both human engineers and agents to consume.

---

## 5. Scope

### In Scope (MVP)

- **Domain:** synthetic healthcare-style entities (Member, Plan, Provider, Eligibility, Claim, ProcedureCode, DiagnosisCode). Explicitly fake — no PHI.
- **Generator core:** deterministic, seedable synthetic data generator producing relationally-consistent records.
- **Validator core:** deterministic domain-consistency checks (e.g., a denied claim must reference a valid procedure code; an inactive member cannot have an active eligibility row).
- **Seeder core:** writes generated records into the Target System Under Test (a small FastAPI + Postgres app shipped in the same repo) via repository methods. No raw SQL from agents.
- **Catalog:** DuckDB over Parquet files in MinIO recording every generated scenario with metadata: `scenario_id`, `test_run_id`, `cleanup_token`, `created_at`, `created_by`, `record_ids`.
- **Reset strategies:** all five (`reset_all`, `reset_run`, `snapshot_restore`, `idempotent_seed`, `cleanup_token`).
- **HTTP API:** FastAPI agent with `POST /test-data/requests`, reset endpoints, audit-log endpoint.
- **Fixture delivery:** Playwright JSON fixture file and pytest Python fixture module generated and returned as part of each scenario response.
- **CLI:** `atdm` command wrapping the HTTP API for engineers who want shell-level access.
- **Tool-bounded planner (rule-based):** parses `scenario` + `constraints` into a deterministic plan; selects generators and validators from a fixed registry. **LLM is OFF by default in MVP.**
- **Audit log:** append-only Parquet file in MinIO; queryable via DuckDB; exposed via `GET /audit/runs/{run_id}`.
- **Demo:** `make demo` runs the full intent → seed → test → reset → audit flow end-to-end against a local stack.
- **Docs:** README ≤ 400 lines, `docs/architecture.md`, `docs/demo-script.md`, `docs/design-decisions.md`, `docs/healthcare-domain-model.md`, CHANGELOG, FEATURES, TODO.

### Out of Scope (this release)

- Real PHI handling, HIPAA compliance, FHIR conformance, EDI parsing.
- Multi-tenant isolation, RBAC, organization model.
- Web UI beyond Swagger and a single audit-log HTML page.
- MCP server (Phase 2).
- Real LLM calls in the default path (Phase 2 — added behind a feature flag).
- Cloud deployment, Kubernetes manifests, Terraform.
- E-commerce domain (Phase 3).
- Vector/RAG retrieval over scenario catalog (Phase 2 — ChromaDB or pgvector).
- Test-run scheduling, queueing, parallelism guarantees beyond single-process FastAPI.

### Future Considerations

- LLM-driven planner with prompt/response logging and reviewer UI.
- Vector retrieval (ChromaDB or pgvector) to match natural-language intent against catalog of past scenarios.
- MCP server exposing the same tool surface to agent runtimes.
- Web dashboard (React) with lineage view.
- Optional MotherDuck cloud mode for the catalog/audit warehouse.
- E-commerce domain pack.
- Masking policies for using real-shaped (but masked) production data.
- Coverage Intelligence: link each generated scenario to a requirement ID and surface which scenarios have / have not been tested.

### Strategy call-outs (Product Strategy Mode)

- **Differentiating:** reset/cleanup discipline, the audit log, the tool-bounded planner architecture, the fact that fixtures are returned as files automation can directly consume. Lead with these.
- **Commodity:** Faker-style data generation, FastAPI scaffold, Docker Compose. Build but do not market.
- **Cut from MVP:**
  - **Real LLM planner** — looks impressive in a slide deck but is fragile, expensive, and adds zero MVP value over a rule-based planner that already returns the same JSON shape. Ship the rule-based planner first; add LLM mode behind a flag in Phase 2 *with* prompt logging and citations.
  - **MotherDuck cloud mode** — distracting; nobody reviewing the portfolio will spin up MotherDuck. DuckDB-local is sufficient.
  - **React dashboard** — costs a week, demos worse than Swagger + a single HTML audit page. Defer.
  - **ChromaDB/pgvector retrieval** — Phase 2. MVP catalog lookup is exact-match on `scenario_id` + tag filter. Adding embeddings before there are 50+ catalog entries is demoware.
- **Risk to flag now:** the demo's persuasive power is **almost entirely the audit log + reset flow**, not the generator. If those two are weak the project is just another Faker wrapper. Invest disproportionately there.

---

## 6. Key Use Cases

### UC-1: Engineer requests a scenario from the CLI

- **Actor:** Alex (automation engineer).
- **Goal:** Get a Playwright fixture for "active member, one denied claim, one pending claim."
- **Trigger:** Alex runs `atdm request --scenario claim_denial_active_member`.
- **Preconditions:** Local stack is up (`make up`). Target SUT is healthy.
- **Main flow:**
  1. CLI POSTs to `/test-data/requests` with the scenario name and constraints.
  2. Planner resolves the scenario name to a deterministic plan.
  3. Validator checks the plan against domain consistency rules.
  4. Generator produces records (member, eligibility, claim, provider, procedure code, diagnosis code).
  5. Seeder writes records to the Target SUT Postgres via repository methods.
  6. Catalog records the scenario; audit log records the run.
  7. API returns scenario response including `playwright_fixture` path, `cleanup_token`, and `test_run_id`.
- **Alternate flows:**
  - **A1 — validator rejects plan:** API returns 422 with the failing rule and the candidate plan; no DB writes occur.
  - **A2 — seeder partial failure:** seeder rolls back the run inside a single transaction; API returns 500 with the run_id; no orphan records.
- **Expected outcome:** Alex has a fixture file on disk and a `test_run_id` she can later use to reset.
- **Quality considerations:** All writes share a single transaction or a saga with compensating actions; partial state is not allowed.

### UC-2: AI testing agent requests a scenario via HTTP

- **Actor:** Aida (AI testing agent).
- **Goal:** Programmatically obtain validated data for a scenario inferred from a user prompt.
- **Trigger:** Agent decides it needs test data and calls `POST /test-data/requests`.
- **Preconditions:** Agent holds the API token; local stack is up.
- **Main flow:** Same as UC-1 but invoked via HTTP, and the response is consumed structurally.
- **Alternate flows:** Same as UC-1.
- **Expected outcome:** Agent receives a structured response sufficient to invoke a downstream test runner.
- **Quality considerations:** Agent invocations are tagged with `invoker=agent` in the audit log so reviewers can filter them.

### UC-3: Test run cleans up after itself by token

- **Actor:** Playwright or pytest test runner.
- **Goal:** Remove all records created during the test, no orphans.
- **Trigger:** Test teardown calls `POST /test-data/runs/{run_id}/reset` with the `cleanup_token`.
- **Preconditions:** A scenario request was previously fulfilled with that `run_id`.
- **Main flow:**
  1. Reset endpoint validates the `cleanup_token`.
  2. Looks up records by `test_run_id`.
  3. Deletes records in dependency order using repository methods.
  4. Marks the audit log entry `status=cleaned`.
- **Alternate flows:**
  - **A1 — token mismatch:** API returns 403; no deletes occur.
  - **A2 — records already deleted:** idempotent; API returns 200 with `status=already_cleaned`.
- **Expected outcome:** Target SUT is identical to its state before the scenario was seeded (excepting auto-incremented IDs).
- **Quality considerations:** Cleanup is verifiable via a diff endpoint or test assertion.

### UC-4: Reviewer inspects what an agent did

- **Actor:** Quinn (QA architect reviewing the portfolio).
- **Goal:** Click through from "an agent invocation" to the prompt, the plan, the records, and the cleanup status.
- **Trigger:** Quinn opens `GET /audit/runs/{run_id}` or browses to `/ui/audit/{run_id}`.
- **Preconditions:** A scenario was previously requested.
- **Main flow:**
  1. Audit endpoint returns the full record: invoker, prompt, plan, validator decisions, records created, cleanup status, timestamps.
  2. Each record links to its source row in the Target SUT and back to its scenario in the catalog.
- **Alternate flows:** none for MVP.
- **Expected outcome:** Quinn can satisfy herself that the agent did nothing it was not authorized to do, and that the workflow is reproducible from the log.
- **Quality considerations:** This use case is the portfolio's strongest single artifact. It must look professional.

### UC-5: Engineer restores baseline before a test suite

- **Actor:** Alex or CI.
- **Goal:** Restore the Target SUT to a known golden state before a full test suite.
- **Trigger:** `make reset-baseline` or `POST /test-data/baseline/restore`.
- **Preconditions:** A baseline snapshot exists (created by `make baseline-snapshot`).
- **Main flow:**
  1. Endpoint drops/truncates Target SUT tables.
  2. Replays the baseline seed.
  3. Re-records the baseline in the audit log.
- **Alternate flows:** none for MVP.
- **Expected outcome:** Target SUT is at the recorded baseline.
- **Quality considerations:** `idempotent_seed` semantics — running baseline restore twice produces the same state, not duplicates.

---

## 7. Functional Requirements

Priorities: **Must**, **Should**, **Could**, **Won't (this release)**. IDs are stable across revisions; do not renumber.

### Scenario request and planning

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-001 | The system shall expose `POST /test-data/requests` accepting a JSON payload with `domain`, `scenario`, `constraints`, and `delivery` fields. | Must | Headline endpoint. |
| FR-002 | The system shall validate every scenario request against a JSON schema before invoking the planner. | Must | Returns 400 on schema failure with field-level errors. |
| FR-003 | The system shall resolve a scenario name to a deterministic plan via a fixed scenario registry. | Must | Registry is YAML-defined under `apps/test-data-agent/app/scenarios/`. |
| FR-004 | The system shall run all registered domain-consistency validators against the resolved plan and reject the request with HTTP 422 if any validator fails. | Must | Validators are deterministic functions; no LLM. |
| FR-005 | The system shall return a single response containing `request_id`, `test_run_id`, `status`, `data` (entity IDs), `fixtures` (paths), and `cleanup` (token + endpoint). | Must | Stable JSON contract — see engineering-handoff.md. |
| FR-006 | The system shall assign a unique `test_run_id` to each scenario request using a sortable identifier (ULID or KSUID). | Must | Sortable so audit log scans are time-ordered. |
| FR-007 | The system shall be capable of operating in **rule-based planner mode** with no outbound LLM calls. | Must | Default for MVP. |
| FR-008 | The system shall expose a feature flag `ATDM_PLANNER=llm` that enables an LLM planner; when enabled, the LLM may only emit a plan in the registered scenario schema, never raw SQL. | Should | Phase 2 enablement; flag present in MVP, implementation may be stub. |

### Generation and seeding

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-010 | The system shall provide deterministic, seedable synthetic generators for Member, Plan, Provider, Eligibility, Claim, ProcedureCode, and DiagnosisCode. | Must | Seed is `test_run_id`-derived so runs are reproducible. |
| FR-011 | The system shall maintain referential integrity across generated records (e.g., a Claim references a Member that exists in the same run). | Must | Enforced by generator orchestration, not by post-hoc DB constraint failures. |
| FR-012 | The system shall write generated records to the Target SUT via repository methods only; no agent-initiated raw SQL. | Must | Hard architectural rule. |
| FR-013 | The system shall complete a single scenario seed within 5 seconds (p95) on the reference local stack for scenarios producing ≤ 20 records. | Should | Measurable performance criterion. |
| FR-014 | The system shall fail a scenario request atomically: either all records exist after the request or none do. | Must | Single DB transaction or saga with compensation. |
| FR-015 | The system shall tag every record it writes to the Target SUT with `test_run_id` (either as a column or via a side-table mapping) so the record is unambiguously attributable to the run that created it. | Must | Without this, `reset_run` cannot work safely. |
| FR-016 | The system shall include explicitly-labelled fake markers (e.g., names sampled from a `FAKE_*` pool, addresses from a fictional state code `ZZ`) so no record can be confused with real production data. | Must | Defensive against accidental data leakage. |

### Fixture delivery

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-020 | The system shall generate a Playwright-compatible JSON fixture for every fulfilled scenario request when `delivery.return_playwright_fixture=true`. | Must | Path returned in response. |
| FR-021 | The system shall generate a pytest-compatible Python fixture module for every fulfilled scenario request when `delivery.return_pytest_fixture=true`. | Must | Path returned in response. |
| FR-022 | The system shall write fixtures to a configurable directory (`ATDM_FIXTURE_DIR`, default `./automation/fixtures/`). | Must | Configurable. |
| FR-023 | The system shall name fixtures `<scenario>_<test_run_id>.{json,py}`. | Should | Deterministic, traceable. |
| FR-024 | The system shall provide a Python fixture library (`atdm.pytest`) that wraps `POST /test-data/requests` for direct pytest consumption. | Should | "First-class pytest experience." |

### Reset and cleanup

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-030 | The system shall expose `POST /test-data/runs/{run_id}/reset` accepting a `cleanup_token`. | Must | Per-run cleanup. |
| FR-031 | The system shall expose `POST /test-data/baseline/restore` restoring the Target SUT to a recorded golden baseline. | Must | Pre-suite reset. |
| FR-032 | The system shall expose `POST /test-data/reset/all` truncating all `test_run_id`-tagged records from the Target SUT. | Must | Heavy-handed reset for demos. |
| FR-033 | The system shall expose `POST /test-data/baseline/snapshot` capturing the current Target SUT state as a baseline. | Should | Used once during demo setup. |
| FR-034 | The system shall make all reset endpoints idempotent: re-invoking the same reset shall produce the same end state with no errors. | Must | `idempotent_seed` semantics. |
| FR-035 | The system shall reject a `reset_run` invocation whose `cleanup_token` does not match the recorded token for that `run_id` (HTTP 403). | Must | Defense against accidental cross-run deletion. |
| FR-036 | The system shall record every reset invocation in the audit log including invoker, run_id, strategy used, records affected, and outcome. | Must | Required for UC-4. |

### Catalog and discovery

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-040 | The system shall persist every fulfilled scenario request to a DuckDB-readable Parquet catalog stored in MinIO. | Must | Single source of truth for "what scenarios exist". |
| FR-041 | The system shall expose `GET /catalog/scenarios` returning all known scenario definitions with their tags and constraints schema. | Must | Discoverability for engineers and agents. |
| FR-042 | The system shall expose `GET /catalog/runs?scenario=<name>&since=<ts>` returning prior runs filterable by scenario and time. | Should | Catalog lookup. |
| FR-043 | The system **shall not** depend on a vector store in MVP. | Must | Embedding-based retrieval is Phase 2. |

### Audit log

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-050 | The system shall append an audit record for every scenario request, validator decision, seeder action, and reset action. | Must | Append-only Parquet. |
| FR-051 | Each audit record shall include: `event_id`, `timestamp`, `test_run_id`, `invoker` (`human:<name>` or `agent:<agent_id>`), `action`, `inputs`, `tools_called`, `outputs`, `status`, `reviewer_decision` (nullable). | Must | Auditable AI output requirement. |
| FR-052 | The system shall expose `GET /audit/runs/{run_id}` returning the full audit trail for a run as JSON. | Must | Powers UC-4. |
| FR-053 | The system shall expose `GET /ui/audit/{run_id}` returning a single-page HTML view of the same trail. | Should | One HTML page, no React. |
| FR-054 | The system shall retain audit records indefinitely on the local filesystem; retention policy is "manual delete only" for MVP. | Could | Production retention is out of scope. |

### CLI

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-060 | The system shall provide an `atdm` CLI with subcommands `request`, `reset`, `baseline-snapshot`, `baseline-restore`, `audit`, `catalog`. | Must | One tool, predictable verbs. |
| FR-061 | The CLI shall read its API base URL and token from `ATDM_API_URL` and `ATDM_API_TOKEN` env vars. | Must | 12-factor. |
| FR-062 | The CLI shall exit non-zero on any API error and print the error body in machine-readable form (`--output json`) or human-readable form (default). | Must | Required for CI use. |

### Demo and developer experience

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| FR-070 | The repository shall provide a `Makefile` with targets `setup`, `up`, `down`, `lint`, `test`, `build`, `demo`, `reset-baseline`, `baseline-snapshot`. | Must | Per project CLAUDE.md. |
| FR-071 | The repository shall provide a `docker-compose.yml` that brings up Postgres, MinIO, the Target SUT, and the ATDM agent. | Must | Per project CLAUDE.md. |
| FR-072 | The `make demo` target shall execute end-to-end: clean state → scenario request → seed → run a sample Playwright/pytest test → reset → display audit log → exit 0. | Must | Demo is the single most important deliverable. |
| FR-073 | The repository shall use **pdm** as the Python package manager. | Must | Per project CLAUDE.md. |

---

## 8. Non-Functional Requirements

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| NFR-001 | The full local stack shall start from `docker compose up` to "ready" (all health checks green) within 60 seconds on a developer Mac/Linux laptop with 16 GB RAM. | Must | Demo performance. |
| NFR-002 | A scenario request producing ≤ 20 records shall complete end-to-end (request → seed → fixture written → response) within 5 seconds (p95) on the reference local stack. | Must | See FR-013. |
| NFR-003 | The system shall run entirely offline after `docker compose pull` and `pdm install`; no outbound network calls shall be required for MVP scenarios. | Must | LLM-off default. Outbound calls only allowed when `ATDM_PLANNER=llm`. |
| NFR-004 | All mutating endpoints shall require an API token via `Authorization: Bearer <token>`; the token is read from `ATDM_API_TOKEN`. Read endpoints shall be open on the local network. | Must | MVP-grade auth; called out as a known limitation. |
| NFR-005 | The system shall be observable: every HTTP request shall emit a structured log line including `request_id`, `test_run_id` (if applicable), `endpoint`, `status`, `latency_ms`. | Must | Structured logging, JSON. |
| NFR-006 | The system shall emit Prometheus-compatible counters and histograms at `/metrics`: `atdm_requests_total`, `atdm_request_latency_seconds`, `atdm_resets_total`, `atdm_seed_records_total`, `atdm_planner_invocations_total{mode=}`. | Should | Observability per Implementation Handoff Mode. |
| NFR-007 | The Python codebase shall pass `ruff` lint and `mypy --strict` (with documented per-file exceptions where unavoidable) under `make lint`. | Must | Code quality bar. |
| NFR-008 | Generator, validator, seeder, and reset modules shall maintain ≥ 80 % line coverage under `make test`. | Must | Coverage bar — measured by `pytest-cov`. |
| NFR-009 | The repository shall include a README ≤ 400 lines that opens with the portfolio story, includes an architecture diagram, demo steps, and links to deeper docs under `docs/`. | Must | Per project CLAUDE.md. |
| NFR-010 | The system shall produce no PHI, no realistic SSNs, no realistic credit-card numbers, and no real provider NPI numbers. | Must | All synthetic data carries a `FAKE_` prefix marker on free-text fields and uses the `ZZ` fictional state code. |
| NFR-011 | The audit log shall be append-only at the application layer; no API surface shall permit deleting or modifying past audit records. | Must | Tamper-evident at the application level. (Filesystem-level tamper-evidence is out of scope.) |
| NFR-012 | The CLI and HTTP API shall produce no emoji in any output, log, or response field. | Must | Per project CLAUDE.md. |
| NFR-013 | All shared system tools (Postgres, MinIO) shall run via Docker Compose locally; no virtual envs inside containers unless a conflict justifies it. | Must | Per project CLAUDE.md. |
| NFR-014 | The repository shall maintain `CHANGELOG.md`, `FEATURES.md`, and `TODO.md` and update them with every merged change. | Must | Per project CLAUDE.md. |
| NFR-015 | The system shall be installable on macOS and Linux via `make setup` with no manual steps beyond installing Docker and pdm. | Must | Reviewer-friendliness. |

---

## 9. Data Requirements

### Major entities (Target SUT — synthetic healthcare domain)

| Entity | Key attributes | Relationships |
|---|---|---|
| **Member** | `member_id` (PK), `status` (active/inactive), `first_name`, `last_name`, `date_of_birth`, `address`, `plan_id` (FK), `test_run_id` | Belongs to a Plan; has many Eligibility rows and many Claims. |
| **Plan** | `plan_id` (PK), `name`, `coverage_type`, `effective_date`, `test_run_id` | Has many Members. |
| **Provider** | `provider_id` (PK), `name`, `network_status` (in/out), `npi_fake`, `test_run_id` | Has many Claims. |
| **Eligibility** | `eligibility_id` (PK), `member_id` (FK), `effective_from`, `effective_to`, `status`, `test_run_id` | Belongs to a Member. |
| **Claim** | `claim_id` (PK), `member_id` (FK), `provider_id` (FK), `procedure_code` (FK), `diagnosis_code` (FK), `status` (paid/denied/pending), `submitted_at`, `denial_reason` (nullable), `test_run_id` | Belongs to a Member and a Provider; references one ProcedureCode and one DiagnosisCode. |
| **ProcedureCode** | `code` (PK), `description`, `is_valid` (bool), `test_run_id` (nullable; some codes are reference data shared across runs) | Referenced by Claims. |
| **DiagnosisCode** | `code` (PK), `description`, `is_valid` (bool), `test_run_id` (nullable) | Referenced by Claims. |

### Major entities (ATDM internal)

| Entity | Key attributes | Notes |
|---|---|---|
| **ScenarioDefinition** | `scenario_id`, `name`, `description`, `constraints_schema_path`, `generators[]`, `validators[]` | YAML-loaded at startup. |
| **ScenarioRequest** | `request_id`, `test_run_id`, `scenario_id`, `constraints`, `invoker`, `status`, `created_at`, `cleanup_token` | Cataloged. |
| **AuditEvent** | `event_id`, `test_run_id`, `timestamp`, `invoker`, `action`, `inputs`, `tools_called`, `outputs`, `status`, `reviewer_decision` | Append-only Parquet, see NFR-011. |

### Data requirements

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| DR-001 | Every Target SUT mutable table shall include a `test_run_id` column (or a side-table mapping). | Must | Powers `reset_run`. |
| DR-002 | Reference tables (`ProcedureCode`, `DiagnosisCode`) shall include a baseline seed that is **shared across runs** and a per-run seed for "invalid" codes used to drive denial scenarios. | Must | Two-tier reference data. |
| DR-003 | The catalog Parquet schema shall be versioned (`schema_version` column) so older catalog files remain readable after schema evolution. | Should | Forward-compatibility. |
| DR-004 | No real PII / PHI is permitted in any generated record. All free-text identifying fields shall be prefixed `FAKE_`. | Must | See NFR-010. |
| DR-005 | The audit log shall be partitioned daily (`audit/dt=YYYY-MM-DD/...`) for efficient DuckDB scans. | Should | Operational hygiene. |
| DR-006 | Generated data shall be traceable end-to-end: every Target SUT row links to a `test_run_id`, which links to a `ScenarioRequest`, which links to all `AuditEvent`s for that run. | Must | This is the Traceability requirement. |
| DR-007 | Cleanup tokens shall be random 128-bit values stored only in the catalog; they are never logged in plain text in the audit log (logged as their SHA-256 hash). | Should | Light defense against cleanup-token reuse from logs. |

---

## 10. AI and Agentic Automation Requirements

There is exactly one AI/agent feature in this system: **the planner**. Everything else is deterministic by design.

### AR-001 — Tool-bounded LLM planner (Phase 2; stub flag in MVP)

| Field | Value |
|---|---|
| **Purpose** | Translate natural-language scenario intent ("active member, denied claim, out-of-network provider") into a registered ScenarioDefinition + constraints object. |
| **Inputs** | Natural-language `intent` string from the request body; the full list of registered ScenarioDefinitions and their constraints schemas (provided to the LLM as a tool catalog). |
| **Tools/APIs invoked** | A fixed set: `list_scenarios()`, `describe_scenario(name)`, `validate_plan(plan)`. The LLM **cannot** call generators, seeders, reset endpoints, or the SUT directly. |
| **Outputs** | A single JSON object matching the same schema the rule-based planner emits: `{scenario, constraints}`. No prose. |
| **HITL checkpoint** | Plan emitted by LLM is run through `validate_plan` (deterministic) before any state mutation. The validator decision is binary: accept or reject. A rejected plan returns HTTP 422 with the rejection reason — no retries inside the request lifecycle. |
| **Write-back scope** | None directly. LLM never mutates state. State mutations are performed only by deterministic seeders invoked after validation passes. |
| **Traceability** | The audit record for the request includes: full LLM prompt, model + version, raw LLM response, parsed plan, validator decision, generator(s) invoked, records created. |
| **Hallucination / confidence handling** | "Confidence" is reduced to a binary: plan parses + plan validates → accept; otherwise → reject. No soft confidence scores; no auto-retry. |
| **Logging** | See FR-051. Prompts are logged in full at MVP scale; redaction policies are deferred. |
| **Permissions** | Only requests bearing a valid API token may invoke the LLM planner; planner mode is process-wide via `ATDM_PLANNER=llm`. There is no per-user LLM enablement in MVP. |
| **Fallback** | If `ATDM_PLANNER=llm` and the LLM call fails (timeout, error, unparseable response), the request falls back to the rule-based planner if the `scenario` field is a known scenario name; otherwise returns HTTP 503. |
| **Risk flag** | LLM mode is **explicitly off in MVP**. Shipping it on would introduce non-determinism into the demo and put outbound network calls on the critical path of a portfolio reviewer's `make demo` run. |

### AR-002 — Rule-based planner (MVP default)

| Field | Value |
|---|---|
| **Purpose** | Translate `{scenario, constraints}` into a deterministic plan by lookup. |
| **Inputs** | `scenario` (string), `constraints` (object). |
| **Tools/APIs invoked** | None outside its own registry. |
| **Outputs** | A `Plan` object: ordered list of `(generator_name, args)` pairs. |
| **HITL** | Not applicable — fully deterministic. |
| **Write-back scope** | None — produces a plan only. |
| **Traceability** | Plan + scenario_id are recorded in the audit log. |
| **Permissions** | Same API token gate as all mutating endpoints. |

### AR-003 — Auditable agent invocation policy

The system shall enforce, at the application layer, that **every agent-initiated state change is mediated by a deterministic validator and recorded with full audit context**. This is not a code-level rule, it is an architectural rule, and it is the single most important AI safety property the system claims.

**Acceptance:** No code path exists that writes to the Target SUT without first passing through a validator-gated generator. This is enforceable by code review and by an architectural-fitness test in `tests/architecture/`.

---

## 11. Integrations

| System | Direction | Trigger | Auth | Failure mode |
|---|---|---|---|---|
| **Target SUT (FastAPI + Postgres, in-repo)** | ATDM → SUT (write via repository methods, read for verification) | Every scenario request and reset | Internal service-to-service token over Docker network | On SUT 5xx, ATDM rolls back the run and returns HTTP 502. |
| **MinIO (S3-compatible)** | ATDM ↔ MinIO (read/write Parquet catalog + audit + fixtures) | Every scenario request, every reset, every audit append | S3 access key/secret from env | On MinIO unreachable, ATDM returns HTTP 503 with a clear message. |
| **DuckDB** | ATDM → DuckDB (read Parquet on demand) | Catalog and audit queries | None (local) | DuckDB is embedded; failure mode is "process crash." |
| **Playwright / pytest** | Consumers → ATDM HTTP API or `atdm.pytest` library | Test setup / teardown | API token | Test fails fast if ATDM unreachable; not silently skipped. |
| **MCP runtime** *(Phase 2)* | MCP client → ATDM | Agent tool invocation | API token | Same as HTTP API. |
| **LLM provider** *(Phase 2, behind flag)* | ATDM → provider (OpenAI / Anthropic / local Ollama) | Only when `ATDM_PLANNER=llm` | Provider API key | On error, fall back to rule-based planner if scenario name is known; else 503. |

---

## 12. Reporting and Analytics

ATDM is not primarily a reporting product, but for portfolio purposes the **audit-log HTML page and a small set of DuckDB-backed reports** are how reviewers see that this is a Quality Intelligence component, not just a fixture factory.

| Audience | Output | Shape |
|---|---|---|
| QA Architect (Quinn) | **Run trail view** | `GET /ui/audit/{run_id}` — single HTML page: invoker, plan, validator decisions, records created, fixtures emitted, cleanup status, timestamps. |
| Author / Maintainer | **Scenario catalog index** | `GET /catalog/scenarios` — JSON; markdown render in `docs/`. |
| Author / Maintainer | **Run history** | DuckDB query against catalog: `SELECT scenario_id, count(*) FROM catalog.runs GROUP BY 1`. Wrapped behind `atdm audit summary`. |
| Reviewer skimming the repo | **README portfolio story** | Static markdown; opens with "what this proves" bullets. |
| Future Coverage Intelligence consumer *(Phase 3)* | **Scenario → requirement linkage** | Each ScenarioDefinition carries an optional `linked_requirement_ids[]` field; a report joins ATDM runs to a requirements file to surface which requirements are scenario-covered. Deferred. |

---

## 13. Acceptance Criteria

One Given/When/Then block per important requirement. Engineering-handoff document carries one block per user story; this section carries the requirement-level criteria.

```
FR-001 / FR-005 — Scenario request happy path
Given a clean Target SUT and a registered scenario "claim_denial_active_member"
When a client POSTs to /test-data/requests with
     { "domain":"healthcare", "scenario":"claim_denial_active_member",
       "constraints":{"member_status":"active","provider_network":"out_of_network",
                      "claim_status":"denied"},
       "delivery":{"seed_target":true,"return_playwright_fixture":true,
                   "cleanup_strategy":"after_test"} }
Then  the response is HTTP 200
And   the response body contains non-null request_id, test_run_id, status="ready"
And   the response body contains data.member_id, data.provider_id, data.claim_id
And   the response body contains fixtures.playwright pointing to an existing file on disk
And   the response body contains cleanup.cleanup_token and cleanup.endpoint
```

```
FR-004 — Validator rejects an impossible plan
Given a registered scenario whose validator forbids "member_status=inactive AND eligibility=active"
When a client POSTs that contradiction in constraints
Then  the response is HTTP 422
And   the body names the failing validator and the offending constraint pair
And   no rows are written to the Target SUT
And   the audit log records action="plan_rejected" for that request_id
```

```
FR-014 — Atomic seeding
Given a scenario whose third generator step always raises an injected error (test mode)
When the scenario is requested
Then  the response is HTTP 500
And   no rows tagged with that test_run_id exist in any Target SUT table
And   the audit log records action="seed_failed" with status="rolled_back"
```

```
FR-030 / FR-035 — Per-run reset with token
Given a previously-fulfilled scenario request with test_run_id=R1 and cleanup_token=T1
When  a client POSTs to /test-data/runs/R1/reset with cleanup_token=T1
Then  the response is HTTP 200 with status="cleaned"
And   no rows tagged with test_run_id=R1 remain in the Target SUT
And   the audit log records action="reset_run" status="cleaned"
And   a second POST with the same token returns HTTP 200 status="already_cleaned"
And   a POST with a wrong token returns HTTP 403 with no DB effect
```

```
FR-031 — Baseline restore
Given a recorded baseline snapshot B0 and arbitrary post-baseline state
When  a client POSTs to /test-data/baseline/restore
Then  the response is HTTP 200
And   the Target SUT row counts and content match B0 (excepting auto-increment IDs)
And   re-invoking /test-data/baseline/restore produces the same end state with status=200
```

```
FR-052 / UC-4 — Reviewer trail
Given any test_run_id from a prior scenario request
When  a client GETs /audit/runs/{run_id}
Then  the response is HTTP 200 with a JSON body containing:
      invoker, planner_mode, prompt (nullable for rule-based), plan,
      validator_decisions[], records_created[], fixtures_emitted[],
      reset_status, started_at, finished_at, duration_ms
And   each records_created entry includes table_name and primary_key
```

```
AR-003 — Architectural fitness: no agent SQL
Given the current codebase
When  the architecture fitness test runs
Then  no module under apps/test-data-agent/app/agents/* contains imports of psycopg, asyncpg, sqlalchemy.engine, or any raw-SQL execution surface
And   every Target SUT write site is reachable only via apps/target-healthcare-api/app/repositories/*
```

```
NFR-001 — Cold-start performance
Given a clean Docker state
When  the developer runs `make up`
Then  all containers report healthy within 60 seconds (p95) over 5 consecutive runs on the reference laptop
```

```
NFR-010 — No PHI in synthetic data
Given any scenario request fulfilled with seed_target=true
When  the resulting Member.address.state and Member.first_name fields are inspected
Then  the state is "ZZ" and the first_name carries the "FAKE_" prefix
And   no field matches a regex for real-looking SSN (^\d{3}-\d{2}-\d{4}$) or real NPI (10-digit Luhn-valid)
```

---

## 14. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| **R1 — Demo is just "Faker + Postgres in Docker."** The differentiating story (audit + reset) is underbuilt and reviewers see a generator, not a platform. | High | High | Invest disproportionately in the audit-log HTML page, the reset endpoints, and the architecture-fitness test. README opens with the audit story, not the generator. | Author |
| **R2 — LLM mode bleeds into MVP and breaks the demo on a reviewer's laptop.** Outbound LLM calls fail, slow down, or require API keys reviewers don't have. | Medium | High | LLM mode is OFF by default, gated by `ATDM_PLANNER=llm`. `make demo` never enables it. Document explicitly that LLM mode is Phase 2. | Author |
| **R3 — Agent path can write to the SUT without going through the validator.** A future refactor adds a shortcut that bypasses the validator, defeating AR-003. | Medium | Critical (to the portfolio claim) | Encode AR-003 as an architectural fitness test (FR-acceptance shown above). Run in CI. | Author |
| **R4 — `test_run_id`-tagging is incomplete on some table** — `reset_run` leaves orphans, breaking the reset story. | Medium | High | Enforce via DB constraint where possible (NOT NULL `test_run_id` on every mutable table); add a regression test that compares row counts pre/post reset and fails on any delta. | Author |
| **R5 — Cleanup-token leakage** — token appears in logs or fixture files; anyone reading the audit log could replay deletion. | Low | Medium | Log only `SHA-256(cleanup_token)` in audit records (DR-007). Tokens are returned in the API response only. | Author |
| **R6 — Scope creep into Phase 2** — MCP, RAG, dashboard, MotherDuck all look attractive mid-build and burn weeks. | High | Medium | The Scope section calls them out explicitly. Treat any Phase 2 work as a separate branch + separate PR. | Author |
| **R7 — Synthetic data accidentally looks real.** A reviewer worries the project handles PHI. | Low | High (perception) | NFR-010 + DR-004: `FAKE_` prefix, `ZZ` state, no real NPI/SSN shapes. Document this in README "Data ethics" section. | Author |
| **R8 — Performance on cold start exceeds 60 s** on slower hardware, undermining "fast demo." | Medium | Medium | Profile `make up`; pin image tags; pre-warm migrations. If unavoidable on lowest-end hardware, document expected times in README. | Author |
| **R9 — Portfolio audience doesn't read past the README.** All this rigor is invisible. | High | Medium | README is the deliverable. Open with the architecture diagram, the demo GIF (or asciinema), the audit log screenshot, and the "what this proves" bullets. Everything else is supporting. | Author |
| **R10 — DuckDB + Parquet over MinIO is novel-looking but adds setup friction.** Reviewer hits a Parquet bug or MinIO config issue and quits. | Low | Medium | Pin versions; ship a one-shot `make smoke` that proves the catalog round-trip works before `make demo`. | Author |

---

## 15. Assumptions

Each assumption is something to validate. Status legend: **Confirmed** = locked on 2026-05-19; **Working** = still an assumption, validate during build.

1. **Working.** The project's primary purpose is portfolio demonstration, not commercial productization.
2. **Working.** The author owns the timeline; there is no external delivery date pressure.
3. **Working.** Single-developer build; no team coordination overhead.
4. **Working.** Reference hardware is a mid-range developer Mac/Linux laptop (≥ 16 GB RAM, Docker installed).
5. **Working.** Reviewers will run `make demo` locally rather than visiting a hosted instance.
6. **Confirmed 2026-05-19** (Question 1). Synthetic healthcare-style domain (Option B) is the chosen MVP domain; e-commerce is Phase 3.
7. **Confirmed 2026-05-19** (Question 2). MVP ships with **rule-based planner only**; LLM mode is a 501-stub feature flag. Real LLM calls are Phase 2.
8. **Working.** MCP server is Phase 2.
9. **Confirmed 2026-05-19** (Question 3). Authentication is a single shared API token for MVP. Multi-user is Phase 3+.
10. **Confirmed 2026-05-19** (Question 4). The Target SUT is a small FastAPI + Postgres app shipped in this repo, not an external service. No second "legacy" SUT in MVP.
11. **Working.** The catalog and audit log are local-first via MinIO + Parquet; cloud (MotherDuck) is Phase 3.
12. **Working.** There is no production deployment; the only deployment target is the developer laptop.
13. **Working.** Test coverage bar is 80 % on core modules (generator/validator/seeder/reset), not on framework glue.
14. **Working.** The architecture-fitness test (no raw SQL from agent code) is enforced in CI.
15. **Working.** `pdm` is the package manager; `ruff` + `mypy --strict` is the lint/type bar.
16. **Confirmed 2026-05-19** (Question 8). Repository is MIT-licensed.
17. **Confirmed 2026-05-19** (Question 9). Playwright fixture format is JSON only for MVP.
18. **Confirmed 2026-05-19** (Question 11). Catalog grows indefinitely in MVP; pruning is a Could-have only if dev friction appears.

---

## 16. Open Questions — RESOLVED 2026-05-19

All 12 questions resolved on 2026-05-19 by accepting the analyst's recommendation. Each entry is now a **decision**, not an open item. Each downstream-impact line names where the decision is reflected in the BRD, the engineering-handoff document, or the plan.

> **Status:** Closed. No outstanding blockers to Phase 0 of [planning/PLAN.md](../planning/PLAN.md).

| # | Question | **DECISION (2026-05-19)** | Downstream impact |
|---|---|---|---|
| 1 | Domain choice for MVP. | **Synthetic healthcare-style (Option B).** E-commerce deferred to Phase 3. | Affirms §5 In Scope, §9 Data Requirements, §17 MVP Recommendation. No edits needed. |
| 2 | LLM mode in MVP. | **OFF by default. Stub flag exists** (`ATDM_PLANNER=llm` returns HTTP 501 with body `{error:{code:"LLM_MODE_NOT_ENABLED"}}`). | Affirms FR-007, FR-008, AR-001 ("Phase 2; stub flag in MVP"). `make demo` shall never set the flag. |
| 3 | Authentication model. | **Single shared API token** via `Authorization: Bearer ${ATDM_API_TOKEN}` on mutating endpoints. Read endpoints open on local network. | Affirms NFR-004. Document the limitation in the README "Security model" section. |
| 4 | Target SUT shape. | **Single FastAPI + Postgres app, in-repo** under `apps/target-healthcare-api/`. No second "legacy" SUT in MVP. | Affirms §11 Integrations and the engineering-handoff Epic A/B layout. |
| 5 | Demo medium. | **Terminal `make demo` + an asciinema cast** committed at `docs/assets/demo.cast` (and an exported `.svg` or `.gif` for embedding in README). | Reflected in PLAN.md Phase 10. Open question is now closed. |
| 6 | Coverage Intelligence linkage. | **Yes — add `linked_requirement_ids[]`** to every ScenarioDefinition YAML from MVP. New requirement FR-044 below. Field is optional but always present (default `[]`). | New FR-044 (catalog section). Engineering-handoff Epic D updated to include the field in ScenarioDefinition. |
| 7 | HTML audit page styling. | **Pico.css via CDN.** Single CSS link tag; no build tooling. | Affirms engineering-handoff Epic E UI section. |
| 8 | License. | **MIT.** Add `LICENSE` file at the repo root during PLAN Phase 0. | PLAN Phase 0 work item added. |
| 9 | Playwright fixture format. | **JSON only for MVP.** TypeScript fixture is a Phase 2 consideration if/when a real Playwright/TypeScript consumer appears. | Affirms FR-020, engineering-handoff Epic D — D1. |
| 10 | Reset semantics on auto-increment IDs. | **Logically equivalent state is sufficient.** `baseline_restore` does **not** reset sequence values; row hashes match modulo PK ID drift. New NFR-016 below captures this. | New NFR-016. PLAN Phase 5 verification command notes "row hash compare excluding PKs". |
| 11 | Catalog growth model. | **Catalog grows indefinitely in MVP.** `make catalog-prune` is a Could-have, implemented only if dev friction appears in Phase 10. | Affirms FR-054 ("manual delete only") and PLAN Phase 10 optional item. |
| 12 | Docker resource limits. | **Yes — set conservative memory limits** in `infra/docker-compose.yml`: Postgres 512MB, MinIO 512MB, Target SUT 512MB, ATDM agent 512MB. New NFR-017 below. | New NFR-017. PLAN Phase 1 work item updated. |

### Consequent additions to this BRD

**FR-044** — The system shall include a `linked_requirement_ids: list[str]` field on every ScenarioDefinition YAML. The field is required at the schema level; an empty list is permitted in MVP. **Priority: Should.** **Acceptance:** Given any ScenarioDefinition file, when the registry loads at startup, then registry validation accepts an empty list and a list of opaque string IDs (e.g., `"FR-001"`, `"REQ-CLM-009"`), and rejects any non-list value. *(Resolves decision #6.)*

**NFR-016** — `POST /test-data/baseline/restore` shall produce a Target SUT state that is **logically equivalent** to the captured baseline: every mutable table's content matches the baseline's content when compared by all non-primary-key columns. Auto-increment sequence values are explicitly **not** reset to baseline values. **Priority: Must.** **Acceptance:** Given a captured baseline B0 and any post-baseline state S, when `baseline/restore` is invoked, then for every mutable table `T` the multiset `SELECT <non_pk_cols> FROM T` equals the same multiset in B0. *(Resolves decision #10.)*

**NFR-017** — `infra/docker-compose.yml` shall set `deploy.resources.limits.memory: 512m` on each of: `postgres`, `minio`, `target-healthcare-api`, `test-data-agent`. **Priority: Should.** **Acceptance:** Given the compose file, when `docker compose config` is rendered, then each named service reports a memory limit of `512m`, and `make up` completes within NFR-001's 60-second budget on the reference laptop under those limits. *(Resolves decision #12.)*

---

## 17. MVP Recommendation

**MVP name:** "ATDM v0.1 — Intent-to-Data, Synthetic Healthcare"

The smallest version that **proves the strategic bet** (auditable agent + reset discipline + framework-native fixtures) is:

1. Docker Compose stack: Postgres, MinIO, Target SUT (FastAPI + Postgres), ATDM agent (FastAPI).
2. One domain (synthetic healthcare) with 5 registered scenarios — at minimum:
   - `active_member_clean` — control case.
   - `claim_denial_active_member` — the headline scenario.
   - `expired_eligibility` — temporal correctness.
   - `out_of_network_pending_claim` — multi-attribute composition.
   - `inactive_member_with_history` — soft-delete semantics.
3. Rule-based planner with the registered scenarios. LLM mode flag exists but is wired to a "not enabled" 501 stub.
4. Generator + validator + seeder for all 7 entities (Member, Plan, Provider, Eligibility, Claim, ProcedureCode, DiagnosisCode).
5. All five reset strategies implemented and CLI-exposed.
6. Audit log to Parquet in MinIO, queryable via DuckDB, exposed at `GET /audit/runs/{run_id}` and `GET /ui/audit/{run_id}`.
7. Playwright JSON fixture + pytest fixture generation.
8. `atdm` CLI with `request`, `reset`, `baseline-snapshot`, `baseline-restore`, `audit`, `catalog`.
9. One Playwright test and one pytest test that consume a fixture, hit the Target SUT, and pass.
10. `make demo` that runs the end-to-end flow in ≤ 90 seconds.
11. Docs: README (≤ 400 lines), architecture.md, demo-script.md, design-decisions.md, healthcare-domain-model.md, CHANGELOG, FEATURES, TODO.
12. CI: `make lint && make test && make build` on push.

**Why this MVP.** It proves four things the strategic bet relies on, and nothing more:

- The **intent-to-data** endpoint shape is real and demoable.
- The **deterministic-validator-gates-everything** architectural rule is enforced (and tested).
- The **reset/cleanup** story works for all five strategies.
- The **audit trail** is clickable and reviewable, not theoretical.

**What it deliberately does not include.** Real LLM calls, vector retrieval, MCP server, React dashboard, MotherDuck, second domain, multi-tenant auth. All Phase 2+.

---

## 18. Roadmap Suggestions

Do not let these bleed back into MVP scope. Each phase is a separate branch and a separate PR series.

### Phase 2 — "Make the agent real" (~2–4 weeks after MVP merges)

- **Enable LLM planner** behind `ATDM_PLANNER=llm`. Add prompt/response logging, model+version pinning, request budget cap.
- **MCP server** exposing `request_scenario`, `reset_run`, `list_scenarios`, `audit_lookup` as MCP tools.
- **Vector retrieval** in the catalog: ChromaDB or pgvector, embedding scenario descriptions, exposed via `POST /catalog/match {intent: "..."}` returning ranked scenario candidates. Used by the LLM planner to ground its proposals.
- **Reviewer UI for plan acceptance** when LLM mode is on — a human-in-the-loop checkpoint between LLM plan and seed.

### Phase 3 — "Scale the surface" (~2 months after MVP)

- **Second domain (e-commerce)** as a separate domain pack to prove the abstraction holds.
- **React dashboard** with lineage view (scenario → run → records → fixtures → audit).
- **Coverage Intelligence linkage**: ScenarioDefinitions carry `linked_requirement_ids[]`; a report joins scenario runs to a requirements file to surface which requirements have been scenario-exercised. This is the moment ATDM becomes a Quality Intelligence component, not just a TDM tool.
- **CI/CD demo via GitHub Actions** showing a real PR using ATDM fixtures.
- **Optional MotherDuck cloud mode** for the catalog/audit warehouse.

### Phase 4 — "Production-grade hardening" (only if there is a real consumer)

- Multi-tenant auth, RBAC.
- Per-organization isolation in catalog and audit store.
- Masking policy engine for taking real-shaped (but masked) production data.
- HIPAA-track features (PHI handling, BAA, audit retention SLAs) — explicitly scoped to a real customer engagement, not portfolio work.

---

## Strategic recommendation — next refinement area

The most leveraged thing to refine next is **the audit trail contract (FR-050 / FR-051 / FR-052)**. That is the single artifact a portfolio reviewer will spend the most time on, and it is currently described in three short bullets. Before any code is written, write a worked example of one full audit record (rule-based path) and one full audit record (LLM path) as illustrative JSON in `docs/design-decisions.md`. That will surface remaining ambiguity in fields, naming, and what counts as a "tool call" — and it will sharpen the headline differentiator of the project.

Recommended sequence after that: (1) confirm answers to open questions 1–5; (2) accept this BRD or revise; (3) review the engineering handoff document; (4) only then begin scaffolding code.
