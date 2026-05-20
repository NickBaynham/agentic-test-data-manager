# TODO

Tracks work not yet shipped. Items move to [FEATURES.md](FEATURES.md) when they land in `main` with green CI.

## Next phase to start

**Phase 4 — Broaden generators, validators, and scenarios.** See [planning/PLAN.md](planning/PLAN.md#phase-4--broaden-generators-validators-and-scenarios).

## Open MVP work (Phases 1–10)

See [planning/PLAN.md](planning/PLAN.md) for the canonical phase list. Each phase has exit criteria and verification commands. Each phase ends in something that runs and is tested.

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
- pdm lockfile pinned by digest.
- pre-commit hooks (ruff, mypy, no-emoji-grep).
- Docker image pinning by digest in `infra/docker-compose.yml`.
