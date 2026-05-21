"""Audit log writer.

One Parquet object per run at `minio://atdm-audit/runs/{run_id}.parquet`.
Append semantics: each new event triggers a read-modify-write of the file.
This is acceptable for Phase 3 scale (a handful of events per run); Phase 9+
can introduce daily-partitioned append-only files if write volume warrants.

Append-only at the API layer (NFR-011): there is no public mutation surface
for past events. The audit endpoint is read-only.

Phase 8 observability: every successful append increments
`atdm_audit_events_total{action, status}` and observes
`atdm_audit_write_latency_seconds`. A failed append increments
`atdm_audit_dropped_events_total` (must remain 0 — the architecture
fitness test asserts this).
"""

from __future__ import annotations

import io
import json
import os
import time
import uuid
from datetime import datetime
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from minio import Minio
from minio.error import S3Error

from app.audit import metrics as audit_metrics

AUDIT_BUCKET = os.environ.get("MINIO_BUCKET_AUDIT", "atdm-audit")

AUDIT_SCHEMA = pa.schema(
    [
        ("event_id", pa.string()),
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("test_run_id", pa.string()),
        ("invoker", pa.string()),
        ("action", pa.string()),
        ("inputs", pa.string()),  # JSON-encoded
        ("tools_called", pa.string()),  # JSON-encoded list of dicts
        ("outputs", pa.string()),  # JSON-encoded
        ("status", pa.string()),
        ("reviewer_decision", pa.string()),  # nullable; empty string when absent
        ("schema_version", pa.int32()),
    ]
)


def _object_key(run_id: str) -> str:
    return f"runs/{run_id}.parquet"


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _read_existing(client: Minio, run_id: str) -> list[dict[str, Any]]:
    try:
        resp = client.get_object(AUDIT_BUCKET, _object_key(run_id))
    except S3Error as e:
        if e.code in ("NoSuchKey", "NoSuchObject"):
            return []
        raise
    try:
        data = resp.read()
    finally:
        resp.close()
        resp.release_conn()
    table = pq.read_table(io.BytesIO(data))
    return list(table.to_pylist())


def _write_all(client: Minio, run_id: str, rows: list[dict[str, Any]]) -> None:
    table = pa.Table.from_pylist(rows, schema=AUDIT_SCHEMA)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)
    data = buf.getvalue()
    client.put_object(
        AUDIT_BUCKET,
        _object_key(run_id),
        io.BytesIO(data),
        length=len(data),
        content_type="application/octet-stream",
    )


def append_event(
    client: Minio,
    *,
    test_run_id: str,
    invoker: str,
    action: str,
    inputs: dict[str, Any] | None = None,
    tools_called: list[dict[str, Any]] | None = None,
    outputs: dict[str, Any] | None = None,
    status: str = "ok",
    reviewer_decision: str | None = None,
) -> None:
    """Append one audit event to the run's Parquet object. Read-modify-write.

    On success, emits `atdm_audit_events_total{action, status}` +1 and
    observes write latency. On failure, increments
    `atdm_audit_dropped_events_total` and re-raises — the caller decides
    whether a missing audit event is recoverable (in practice, callers
    propagate the exception).
    """
    started_at = time.monotonic()
    try:
        existing = _read_existing(client, test_run_id)
        existing.append(
            {
                "event_id": str(uuid.uuid4()),
                "timestamp": datetime.utcnow(),
                "test_run_id": test_run_id,
                "invoker": invoker,
                "action": action,
                "inputs": _json(inputs or {}),
                "tools_called": _json(tools_called or []),
                "outputs": _json(outputs or {}),
                "status": status,
                "reviewer_decision": reviewer_decision or "",
                "schema_version": 1,
            }
        )
        _write_all(client, test_run_id, existing)
    except Exception:
        audit_metrics.record_event_dropped()
        raise
    else:
        audit_metrics.record_event_written(
            action=action,
            status=status,
            latency_seconds=time.monotonic() - started_at,
        )


def read_events(client: Minio, test_run_id: str) -> list[dict[str, Any]]:
    """Return all audit events for a run, chronological order, with JSON
    fields parsed back to Python objects."""
    rows = _read_existing(client, test_run_id)
    parsed = []
    for row in rows:
        parsed.append(
            {
                "event_id": row["event_id"],
                "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
                "test_run_id": row["test_run_id"],
                "invoker": row["invoker"],
                "action": row["action"],
                "inputs": json.loads(row["inputs"]) if row["inputs"] else {},
                "tools_called": json.loads(row["tools_called"]) if row["tools_called"] else [],
                "outputs": json.loads(row["outputs"]) if row["outputs"] else {},
                "status": row["status"],
                "reviewer_decision": row["reviewer_decision"] or None,
                "schema_version": row["schema_version"],
            }
        )
    return parsed
