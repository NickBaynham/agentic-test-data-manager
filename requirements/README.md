# Requirements — Agentic Test Data Manager (ATDM)

This directory holds the requirements artifacts for the Agentic Test Data Manager (ATDM) — a local-first, portfolio-grade test data management platform with a tool-bounded agent layer.

## What is here

| File | Purpose | Audience |
|---|---|---|
| [concept.md](./concept.md) | Original product concept and stack recommendation. The starting point. | Author, anyone who wants the "why this project" pitch. |
| [BRD.md](./BRD.md) | Business Requirements Document — the canonical 18-section analysis. Goals, users, scope, FR / NFR / DR / AR / IR, acceptance criteria, risks, MVP recommendation, roadmap. Product Strategy Mode opinions are baked in. | Product, QA Architect, anyone deciding what to build. |
| [engineering-handoff.md](./engineering-handoff.md) | Implementation-ready breakdown — epics, user stories, API endpoints, data model deltas, services, test cases, observability, security, project-wide Definition of Done. Designed to paste into Jira / GitHub Issues / a coding-agent prompt without translation. | Engineer or coding agent scaffolding the project. |

## How to use these documents

1. **Read [concept.md](./concept.md)** for the original framing.
2. **Read [BRD.md](./BRD.md)** to understand goals, users, scope, and the strategic bet. The pre-flight section restates the idea, names assumptions, and lists the five open questions that most need answers. Open Questions 1–5 in Section 16 are the highest-priority items to confirm.
3. **Read [engineering-handoff.md](./engineering-handoff.md)** before writing code. The "Implementation sequence" at the bottom is the suggested small-step order.

## Strategic summary in one paragraph

The differentiating bet is **reset/cleanup discipline + auditable agent invocations**, not synthetic data generation. The MVP ships with a rule-based planner (LLM mode is Phase 2, off by default), one synthetic healthcare domain, all five reset strategies, an append-only audit log with a server-rendered HTML trail view, and Playwright + pytest fixture emitters. The single most important deliverable is the audit-trail experience — a reviewer should be able to click from "an agent invocation" through to the plan, the validator decisions, the records created, the fixtures emitted, and the cleanup status.

## Next refinement step

Before scaffolding code: write one full worked-example audit record (rule-based path) as illustrative JSON in `docs/design-decisions.md`. That surfaces ambiguity in fields and what counts as a "tool call." See BRD Section 17 "Strategic recommendation — next refinement area" for the rationale.

## Status

All 12 BRD §16 open questions resolved on **2026-05-19** by accepting the analyst's recommendations. See the resolved decision table at the top of [BRD §16](./BRD.md#16-open-questions--resolved-2026-05-19). No blockers remain to beginning Phase 0 of [planning/PLAN.md](../planning/PLAN.md).

## Conventions

- Requirement IDs (`FR-NNN`, `NFR-NNN`, `DR-NNN`, `AR-NNN`, `IR-NNN`) are stable across revisions. Do not renumber.
- "Shall" denotes a mandatory system behavior; "should" denotes a recommendation. Avoid "will," "may," "can" in normative statements.
- Priorities use MoSCoW: Must, Should, Could, Won't (this release).
- No emoji in any document under this directory, per the project CLAUDE.md.
