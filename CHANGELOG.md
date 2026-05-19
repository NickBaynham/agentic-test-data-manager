# Changelog

All notable changes to this project are recorded here. Newest first.

## [Unreleased]

### Added — 2026-05-19 — Phase 0 scaffold

- `pyproject.toml` (pdm-managed) declaring Python 3.12 and dev deps: `ruff`, `mypy`, `pytest`, `pytest-cov`, `httpx`.
- `mypy.ini` with `strict = True` against the project source paths.
- `Makefile` with stub targets: `setup`, `lint`, `test`, `build`, `up`, `down`, `demo`, `smoke`, `baseline-snapshot`, `reset-baseline`, `clean`. Stack and demo targets are placeholders that exit non-zero with a "not yet implemented — Phase N" notice.
- Top-level directory skeleton per [planning/PLAN.md](planning/PLAN.md) Phase 0: `apps/test-data-agent/`, `apps/target-healthcare-api/`, `automation/`, `data/`, `docs/`, `infra/`, `tests/`.
- `__init__.py` placed in every Python package directory.
- `.gitkeep` placed in data / infra / asset directories.
- `LICENSE` — MIT, copyright Nick Baynham 2026 (per BRD §16 decision #8).
- `README.md` placeholder with status banner, CI badge, doc index, quickstart, security and data-ethics sections.
- `CHANGELOG.md`, `FEATURES.md`, `TODO.md` per project CLAUDE.md.
- `.env.example` with the env vars MVP will use; secrets stay out of git.
- `.gitignore` for Python / pdm / virtualenv / coverage / OS artifacts.
- `.github/workflows/ci.yml` running lint, test, and architecture jobs on push and PR.
- `tests/test_truth.py` — single trivial passing test confirming the test harness runs.

### Decisions baked in

- 2026-05-19: All 12 BRD §16 open questions resolved by accepting the analyst's recommendations. See [requirements/BRD.md §16](requirements/BRD.md#16-open-questions--resolved-2026-05-19) for the decision table.

### Lessons learned

- 2026-05-19 — **mypy duplicate-module trap.** The documented layout has two Python packages literally named `app` (one per `apps/` subproject). Running mypy against both in a single invocation triggers `Duplicate module named "app"` and aborts. Resolution: `mypy.ini` sets `explicit_package_bases = True` + `namespace_packages = True`, and `make lint` runs mypy in three separate passes (one per source root). Captured in [planning/PLAN.md Phase 0 "Known pitfall"](planning/PLAN.md) so future replays of Phase 0 avoid it.
- 2026-05-19 — **Default host ports collide with other local stacks.** A common dev laptop already runs Postgres on `5432` and MinIO on `9000`/`9001` for unrelated projects. Phase 1 would have failed `make up` with `bind: address already in use`. Resolution: shifted host ports to `55432` (Postgres), `19000`/`19001` (MinIO), `18000` (Target SUT), `18001` (ATDM agent). Container-internal ports are unchanged. Locked into [planning/PLAN.md Phase 1 host port mapping table](planning/PLAN.md#phase-1--docker-compose-postgres-minio-two-service-stubs); referenced from README Quickstart and `.env.example`.
