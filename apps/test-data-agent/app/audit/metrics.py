"""Audit-writer Prometheus metrics.

Three metrics per PLAN.md Phase 8 observability requirements:

  atdm_audit_events_total{action, status}     counter
  atdm_audit_write_latency_seconds            histogram
  atdm_audit_dropped_events_total             counter — must remain 0

We use `prometheus_client` for the in-process registry. `render_prometheus_text()`
is appended to the agent's /metrics body alongside the existing atdm_up gauge.
"""

from __future__ import annotations

from prometheus_client import REGISTRY, Counter, Histogram, generate_latest

AUDIT_EVENTS_TOTAL = Counter(
    "atdm_audit_events_total",
    "Audit events written, labelled by action and status.",
    labelnames=["action", "status"],
)

AUDIT_WRITE_LATENCY_SECONDS = Histogram(
    "atdm_audit_write_latency_seconds",
    "Latency of a single audit append (read-modify-write of the run's Parquet object).",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# Self-monitoring: must remain 0. Phase 8 acceptance — if non-zero in CI,
# the build fails (the audit-append-only fitness test asserts this).
AUDIT_DROPPED_EVENTS_TOTAL = Counter(
    "atdm_audit_dropped_events_total",
    "Audit events that the writer failed to persist (durability violations).",
)


def record_event_written(action: str, status: str, latency_seconds: float) -> None:
    """Called by audit.writer after a successful append."""
    AUDIT_EVENTS_TOTAL.labels(action=action, status=status).inc()
    AUDIT_WRITE_LATENCY_SECONDS.observe(latency_seconds)


def record_event_dropped() -> None:
    """Called by audit.writer when an append fails durability."""
    AUDIT_DROPPED_EVENTS_TOTAL.inc()


def render_prometheus_text() -> str:
    """Return the full prometheus_client text exposition for the global registry."""
    return generate_latest(REGISTRY).decode("utf-8")
