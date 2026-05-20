"""Catalog: one Parquet object per ScenarioRequest stored in MinIO.

Schema is kept simple in Phase 3. The catalog stores enough state to verify
a cleanup token (DR-007: hashed, never plain), look up which scenario was run,
and (Phase 5+) participate in `reset_all` and `baseline_restore`.
"""

from __future__ import annotations

import hashlib
import io
import os
from datetime import datetime
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from minio import Minio
from minio.error import S3Error

CATALOG_BUCKET = "atdm-catalog"

CATALOG_SCHEMA = pa.schema(
    [
        ("test_run_id", pa.string()),
        ("request_id", pa.string()),
        ("scenario_id", pa.string()),
        ("created_at", pa.timestamp("us", tz="UTC")),
        ("cleanup_token_sha256", pa.string()),
        ("status", pa.string()),
        ("invoker", pa.string()),
        ("schema_version", pa.int32()),
    ]
)


def sha256_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def make_minio_client() -> Minio:
    endpoint = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
    # Minio() expects host[:port] without scheme; strip if present.
    if endpoint.startswith("http://"):
        host = endpoint[len("http://") :]
        secure = False
    elif endpoint.startswith("https://"):
        host = endpoint[len("https://") :]
        secure = True
    else:
        host = endpoint
        secure = False

    return Minio(
        host,
        access_key=os.environ.get("MINIO_ROOT_USER", "atdm"),
        secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "atdm-dev-only"),
        secure=secure,
    )


def _object_key(run_id: str) -> str:
    return f"runs/{run_id}.parquet"


def write_run(
    client: Minio,
    *,
    test_run_id: str,
    request_id: str,
    scenario_id: str,
    cleanup_token_plain: str,
    invoker: str,
    status: str = "ready",
) -> None:
    """Write the catalog row for a scenario request.

    The cleanup token is stored only as its sha256 hash (DR-007). Callers MUST
    return the plain token to the user in the API response and never persist it.
    """
    row: dict[str, Any] = {
        "test_run_id": test_run_id,
        "request_id": request_id,
        "scenario_id": scenario_id,
        "created_at": datetime.utcnow(),
        "cleanup_token_sha256": sha256_token(cleanup_token_plain),
        "status": status,
        "invoker": invoker,
        "schema_version": 1,
    }
    table = pa.Table.from_pylist([row], schema=CATALOG_SCHEMA)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)
    data = buf.getvalue()
    client.put_object(
        CATALOG_BUCKET,
        _object_key(test_run_id),
        io.BytesIO(data),
        length=len(data),
        content_type="application/octet-stream",
    )


def read_run(client: Minio, test_run_id: str) -> dict[str, Any] | None:
    """Return the catalog row for the given run, or None if absent."""
    try:
        resp = client.get_object(CATALOG_BUCKET, _object_key(test_run_id))
    except S3Error as e:
        if e.code in ("NoSuchKey", "NoSuchObject"):
            return None
        raise
    try:
        data = resp.read()
    finally:
        resp.close()
        resp.release_conn()
    table = pq.read_table(io.BytesIO(data))
    if table.num_rows == 0:
        return None
    row: dict[str, Any] = table.to_pylist()[0]
    return row


def update_status(client: Minio, test_run_id: str, status: str) -> None:
    """Read the existing row, update its status, write it back. Used by reset."""
    existing = read_run(client, test_run_id)
    if existing is None:
        return
    existing["status"] = status
    table = pa.Table.from_pylist([existing], schema=CATALOG_SCHEMA)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    buf.seek(0)
    data = buf.getvalue()
    client.put_object(
        CATALOG_BUCKET,
        _object_key(test_run_id),
        io.BytesIO(data),
        length=len(data),
        content_type="application/octet-stream",
    )
