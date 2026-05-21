Yes — I strongly recommend building this. It is portfolio-perfect because it connects your existing strengths:

* QA architecture
* API automation
* agentic testing
* test data management
* Python/FastAPI
* Playwright/API testing
* RAG/vector search
* CI/CD
* resettable test environments
* “quality intelligence” thinking

My recommendation: build a project called something like:

Agentic Test Data Manager

Or more portfolio-branded:

Test Data Agent: AI-Powered Test Data Management for Automation

The idea: a small but impressive platform where an automation engineer or AI test agent can request valid test data by intent, scenario, or constraints.

Example:

“Give me an active healthcare member with dependents, valid coverage, one denied claim, and one pending claim.”

The system returns:

{
  "scenario_id": "claim-denial-active-member-001",
  "member": {...},
  "provider": {...},
  "claim": {...},
  "eligibility": {...},
  "api_seed_script": "...",
  "playwright_fixture": "...",
  "cleanup_token": "..."
}

That is exactly the kind of thing a recruiter or hiring manager can understand quickly.

⸻

My top recommendation

Build it as a local-first lakehouse + API test target + agent layer.

Recommended stack

Layer	Tool	Why
App/API	FastAPI	Fits your Python/API architecture story
Transactional DB	Postgres	Realistic source-of-record for test target
Data lake/object store	MinIO	Local S3-compatible object storage
Analytical warehouse	DuckDB	Lightweight SQL over Parquet/CSV/JSON
Optional cloud warehouse	MotherDuck free tier	Cloud DuckDB option; current pricing page shows a free Lite plan with 10GB storage and included compute
Vector/RAG	ChromaDB or pgvector	For scenario/document retrieval
Test automation	Playwright + pytest	Demonstrates real test consumption
Containers	Docker Compose	Easy demo and reset
Test isolation	Testcontainers or reset API	Shows professional test environment control

DuckDB is a great fit because it can query Parquet, JSON, S3, and other lake-style data sources directly, making it ideal for a portfolio-friendly “mini warehouse” without needing expensive infrastructure.  ￼

MinIO is useful because it gives you S3-compatible object storage locally, so you can model data-lake behavior without paying AWS bills or requiring recruiters to set up cloud accounts.  ￼

MotherDuck is worth considering only as an optional “cloud warehouse mode”; its pricing page currently lists a free Lite plan with 10GB storage and included compute, which is enough for a demo.  ￼

⸻

The project concept

What the system does

The Test Data Agent provides test data to automation frameworks and AI testing agents.

It supports:

1. Scenario-based data requests
    * “Create a paid user”
    * “Create a denied claim”
    * “Create an account with expired subscription”
    * “Create an order with failed payment”
2. Synthetic data generation
    * Generates realistic fake data.
    * Avoids real PII/PHI.
    * Can create linked relational records.
3. Data discovery
    * Finds existing reusable data.
    * Searches cataloged test data sets.
    * Uses metadata and embeddings to match intent.
4. Data seeding
    * Inserts data into a target system DB.
    * Or calls target APIs to create data.
    * Or produces SQL/API scripts for automation.
5. Reset/cleanup
    * Reset before test suite.
    * Cleanup after scenario.
    * Roll back by test run ID.
    * Restore golden baseline.
6. Automation consumption
    * Playwright fixtures.
    * Pytest fixtures.
    * API endpoint.
    * CLI.
    * MCP tool later, if you want the “agentic” part to really shine.

⸻

Best demo domain

I would not start with healthcare payer workflows unless you want to spend a lot of time learning EDI and claims.

Instead, build a clean generic domain first:

Option A: E-commerce test target

This is easiest for recruiters to understand.

Entities:

* Customer
* Address
* Product
* Cart
* Order
* Payment
* Shipment
* Refund

Example scenarios:

* New customer with empty cart
* Returning customer with order history
* Customer with failed payment
* Order stuck in fulfillment
* Refund pending
* Discount code expired
* Product out of stock

This is the fastest route to a compelling demo.

Option B: Healthcare-inspired but simplified

This maps better to the recruiter JD, but keep it fake and lightweight.

Entities:

* Member
* Plan
* Provider
* Eligibility
* Claim
* Procedure code
* Diagnosis code

Example scenarios:

* Active member with valid coverage
* Inactive member
* Claim denied for invalid code
* Claim pending review
* Provider out of network
* Prior authorization required

I would probably choose Option B, but make it explicitly:

“Synthetic healthcare-style payer test domain — no real PHI, no real claims data.”

That lets you speak to the job description without pretending you built Facets.

⸻

Recommended architecture

┌──────────────────────────────┐
│ Test Request                  │
│ "Need active member w/ claim" │
└───────────────┬──────────────┘
                ↓
┌──────────────────────────────┐
│ Test Data Agent API           │
│ FastAPI                       │
└───────────────┬──────────────┘
                ↓
┌──────────────────────────────┐
│ Planner / Resolver            │
│ Rules + LLM optional          │
└───────┬───────────────┬──────┘
        ↓               ↓
┌──────────────┐   ┌────────────────┐
│ Data Catalog │   │ Synthetic Data │
│ DuckDB/RAG   │   │ Generator      │
└──────┬───────┘   └───────┬────────┘
       ↓                   ↓
┌──────────────────────────────────┐
│ Data Lake / Warehouse             │
│ MinIO + Parquet + DuckDB           │
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│ Target System Under Test          │
│ FastAPI app + Postgres            │
└────────────────┬─────────────────┘
                 ↓
┌──────────────────────────────────┐
│ Playwright / Pytest / API Tests   │
└──────────────────────────────────┘

The key portfolio message:

“The agent does not merely generate random fake data. It plans, validates, seeds, tracks, and resets data for repeatable automation.”

That sentence matters.

⸻

The most impressive feature: intent-to-data

Build an endpoint like this:

POST /test-data/requests

Request:

{
  "domain": "healthcare",
  "scenario": "claim_denial",
  "constraints": {
    "member_status": "active",
    "provider_network": "out_of_network",
    "claim_status": "denied",
    "diagnosis_code": "valid",
    "procedure_code": "invalid"
  },
  "delivery": {
    "seed_target": true,
    "return_playwright_fixture": true,
    "cleanup_strategy": "after_test"
  }
}

Response:

{
  "request_id": "tdr_12345",
  "test_run_id": "run_2026_05_19_001",
  "status": "ready",
  "data": {
    "member_id": "M-100042",
    "provider_id": "P-90012",
    "claim_id": "C-70088"
  },
  "fixtures": {
    "playwright": "fixtures/claim_denial_active_member.json",
    "pytest": "fixtures/claim_denial_active_member.py"
  },
  "cleanup": {
    "cleanup_token": "cleanup_abc123",
    "endpoint": "/test-data/runs/run_2026_05_19_001/reset"
  }
}

That is very demo-able.

⸻

Project modules

I’d organize the repo like this:

agentic-test-data-manager/
  README.md
  docker-compose.yml
  Makefile
  apps/
    test-data-agent/
      app/
        main.py
        api/
        agents/
        generators/
        validators/
        seeders/
        catalog/
        reset/
      tests/
    target-healthcare-api/
      app/
        main.py
        models/
        routes/
        db/
      tests/
    web-dashboard/
      package.json
      src/
  data/
    seed/
    synthetic/
    parquet/
    catalogs/
  automation/
    playwright/
    pytest-api/
  docs/
    architecture.md
    demo-script.md
    recruiter-summary.md
    design-decisions.md
    healthcare-domain-model.md

⸻

Minimum viable version

For a first portfolio release, do not overbuild.

Version 1 should include:

* FastAPI Test Data Agent
* FastAPI target app
* Postgres database
* MinIO object storage
* DuckDB querying Parquet files
* Synthetic member/claim/provider generator
* Scenario request endpoint
* Seed target database endpoint
* Reset by test run ID
* Playwright or pytest test consuming generated data
* README with architecture diagram and demo steps

That alone is excellent.

Version 2 can add:

* LLM planning
* RAG over scenario catalog
* ChromaDB/pgvector
* MCP server
* Web dashboard
* Data lineage
* Masking policies
* CI/CD pipeline
* GitHub Actions demo

⸻

How to make it “agentic” without making it fragile

This is important.

Do not let the LLM directly write arbitrary SQL into the database.

Instead:

LLM suggests scenario plan
        ↓
Deterministic validator checks plan
        ↓
Approved generator creates data
        ↓
Seeder uses controlled repository/service methods
        ↓
Audit log records what happened

That demonstrates mature AI engineering.

You can describe the agent as having tools:

search_catalog()
generate_synthetic_member()
generate_claim()
validate_domain_consistency()
seed_target_system()
create_playwright_fixture()
reset_test_run()

That is the right level of “agentic.” Practical, guarded, credible.

⸻

Reset strategies to demonstrate

You should include more than one reset strategy because this is a big part of professional test data management.

Strategy	What it shows
reset_all	Restore the target DB to a baseline
reset_run	Remove only records created during one test run
snapshot_restore	Restore from a known golden state
idempotent_seed	Re-running seed does not duplicate bad data
cleanup_token	Tests can clean up after themselves

A great endpoint:

POST /test-data/runs/{run_id}/reset

And another:

POST /test-data/baseline/restore

This maps directly to real-world automation pain.

⸻

The portfolio story

Your README should open with something like:

This project demonstrates an agentic test data management platform for AI-assisted software testing. It allows test automation frameworks and AI test agents to request scenario-specific, validated, synthetic test data, seed a target system, generate fixtures, and reset test environments safely.

Then include:

What this proves

* I can design AI-enabled QA architecture.
* I can build reusable automation frameworks.
* I understand test data lifecycle management.
* I can integrate LLMs safely with deterministic tools.
* I can design APIs for autonomous testing agents.
* I understand resettable, repeatable test environments.
* I can connect quality intelligence with real automation execution.

That’s directly aligned with the QA Architect role.

⸻

My recommendation

Build the project as:

Synthetic Healthcare Test Data Agent

Using:

* FastAPI
* Postgres
* DuckDB
* MinIO
* Parquet
* ChromaDB or pgvector
* Playwright
* Docker Compose
* Optional MotherDuck mode

Why this version?

Because it maps to the job description without requiring you to become a full Databricks/Snowflake/EDI expert first.

The killer demo would be:

1. Start local stack with Docker.
2. Open dashboard or Swagger.
3. Request: “active member with denied claim.”
4. Agent generates validated synthetic data.
5. Agent seeds target healthcare API.
6. Playwright/API test runs using returned fixture.
7. Test passes.
8. Reset endpoint cleans the test data.
9. Audit log shows scenario, records, lineage, and cleanup status.

That is a seriously strong portfolio artifact.

I’d make this your next flagship project for testingwithagents.com.
