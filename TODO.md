# TODO

Tracks work not yet shipped. Items move to [FEATURES.md](FEATURES.md) when they land in `main` with green CI.

## Status

**MVP is complete (2026-05-21).** All 10 phases shipped. The project-wide
Definition of Done is fully ticked in
[planning/PLAN.md Phase 10](planning/PLAN.md#phase-10--hardening-polish-and-merge-to-main).

Post-MVP work lives in the candidate sections below. See
[requirements/BRD.md §18 Roadmap](requirements/BRD.md) for the strategic
phasing.

## Original MVP plan (all shipped)

See [planning/PLAN.md](planning/PLAN.md) for the canonical phase list. Each phase has exit criteria and verification commands. Each phase ends in something that runs and is tested.

## Outstanding from MVP phases

Items that were explicitly deferred or marked partial during MVP work but
never ticketed. None block the MVP's claim — the project-wide Definition
of Done passes — but each one is real work a future maintainer could
profitably pick up.

- **Fresh-clone reviewer dry-run on a non-dev machine** (Phase 10 work
  item, skipped). The PLAN said: "Run a fresh-clone reviewer dry-run on
  a separate machine (or a fresh Docker context). Time `make up` and
  `make demo`. Adjust if either exceeds NFR-001 (60s) or A2 (90s)." I
  didn't do this — measurements were taken on the dev host, where the
  brew tools, pdm cache, and Docker images were already warm. Action:
  spin up a clean macOS / Linux VM, run `make setup && make up && make
  demo` from a fresh `git clone`, and record measured times in
  `CHANGELOG.md` Lessons learned.

- **`GET /catalog/runs?scenario=&since=` endpoint (FR-042 — Should)**.
  Phase 7 shipped `GET /catalog/scenarios` (FR-041 — Must). FR-042
  is "Should" priority. Marked "Phase 7+" in the inline comment in
  `apps/test-data-agent/app/api/catalog.py` but never added to any
  tracker. Action: enumerate `s3://atdm-catalog/runs/*.parquet`,
  filter by scenario + timestamp, return as JSON list.

- **D3 cross-fixture verification at the integration layer**
  (`tests/integration/test_phase7_cli_and_pytest.py:178`). Phase 7
  removed an integration test that tried to verify "the `@atdm_scenario`
  teardown actually emits a `reset_completed` audit event" because
  `pytest.request.addfinalizer` runs BEFORE the `atdm_data` fixture's
  yield-teardown. A session-scoped tracker fixture that records run
  IDs during tests and verifies them after the session would close this
  gap. Currently covered at the unit level only.

- **Playwright CI job** (Phase 7 marked PARTIAL). The example Playwright
  TypeScript test exists and runs locally via `make playwright-test`,
  but it isn't part of any CI workflow because the Node + Chromium
  install adds ~3 minutes to the build for one test. Action: add a
  `playwright` CI job that runs only on `tests/playwright/**` path
  changes (or on a manual workflow dispatch), so it doesn't pay the
  cost on every push.

- **DuckDB analytical layer over catalog + audit Parquet**. The PLAN.md
  and BRD called for DuckDB as the analytical query engine ("lightweight
  SQL over Parquet/CSV/JSON"). The MVP ships PyArrow for read/write only.
  DuckDB integration would enable things like "how many denied claims
  were generated in the last 24 hours?" via a single SQL query against
  the audit Parquet, which is the natural Phase 3 next step toward the
  Coverage Intelligence story.

- **Architecture diagram as PNG for non-GitHub viewers** (Phase 9
  deferred). The mermaid diagram in `docs/architecture.md` renders
  natively on GitHub but won't render in plain Markdown viewers or PDF
  exports. Use `mermaid-cli` (`@mermaid-js/mermaid-cli`) to export
  `docs/assets/architecture.png` if a non-GitHub audience matters.

## Phase 2 candidate items (post-MVP)

- Enable LLM planner mode behind `ATDM_PLANNER=llm` with prompt/response logging, model+version pinning, and a request budget cap.
- MCP server exposing `request_scenario`, `reset_run`, `list_scenarios`, `audit_lookup`.
- Vector retrieval in the catalog (ChromaDB or pgvector); `POST /catalog/match {intent: "..."}`.
- Reviewer UI for plan acceptance when LLM mode is on (human-in-the-loop checkpoint between LLM plan and seed).

## Phase 3+ candidate items

- E-commerce domain pack.
- React dashboard with lineage view.
- Coverage Intelligence report joining scenario runs to a requirements file.
- GitHub Actions demo of a real PR using ATDM fixtures.
- Optional MotherDuck cloud mode for catalog/audit warehouse.
- TypeScript Playwright fixture format (decision #9 currently JSON-only for MVP).

## Phase 4 — production-grade hardening (only if a real consumer appears)

- Multi-tenant auth, RBAC.
- Per-organization isolation in catalog and audit store.
- Masking policy engine for taking real-shaped (but masked) production data.
- HIPAA-track features explicitly scoped to a real customer engagement.

## Could-haves / quality-of-life

- `make catalog-prune` for older runs (BRD §16 decision #11 — only if dev friction appears).
- pdm lockfile pinned by package digest (Python `hash:sha256` per-package, the pip-style lock). Currently `pdm.lock` is committed but doesn't include sha256 hashes; adding them gives byte-identical reinstalls.
- ~~pre-commit hooks (ruff, mypy, no-emoji-grep).~~ Done in Phase 10. See `.pre-commit-config.yaml`.
- ~~Docker image pinning by digest in `infra/docker-compose.yml`.~~ Done in Phase 10.
