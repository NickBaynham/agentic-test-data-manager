"""Baseline snapshot/restore via PyArrow + MinIO.

Schema-agnostic — the snapshotter reads whatever columns exist in each table
and writes them to Parquet. Restore is the reverse. This keeps the module
short and resilient to schema changes within Phase 5; if Phase 6+ adds new
columns to existing tables, the snapshot/restore code does not change.
"""

from __future__ import annotations

import io
import json
import os
from datetime import UTC, datetime
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from minio import Minio
from minio.error import S3Error

from app.db.session import DbConn, connection
from app.reset.strategies import FK_INSERT_ORDER

CATALOG_BUCKET = os.environ.get("MINIO_BUCKET_CATALOG", "atdm-catalog")
BASELINE_PREFIX = "baselines"
MANIFEST_NAME = "manifest.json"


def make_minio_client() -> Minio:
    endpoint = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
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


def _object_prefix(baseline_id: str) -> str:
    return f"{BASELINE_PREFIX}/{baseline_id}"


def _manifest_key(baseline_id: str) -> str:
    return f"{_object_prefix(baseline_id)}/{MANIFEST_NAME}"


def _table_key(baseline_id: str, table: str) -> str:
    return f"{_object_prefix(baseline_id)}/{table}.parquet"


async def _dump_table_to_parquet(conn: DbConn, table: str, minio: Minio, baseline_id: str) -> int:
    rows = await conn.fetch(f"SELECT * FROM {table}")  # noqa: S608
    records: list[dict[str, Any]] = [dict(row) for row in rows]
    pa_table = pa.Table.from_pylist(records)
    buf = io.BytesIO()
    pq.write_table(pa_table, buf, compression="snappy")
    buf.seek(0)
    data = buf.getvalue()
    minio.put_object(
        CATALOG_BUCKET,
        _table_key(baseline_id, table),
        io.BytesIO(data),
        length=len(data),
        content_type="application/octet-stream",
    )
    return len(records)


async def snapshot_baseline(baseline_id: str) -> dict[str, Any]:
    """Write each of the 7 tables to Parquet under baselines/{baseline_id}/.

    Writes a manifest.json with the captured timestamp, table list, and row
    counts so restore is self-describing.
    """
    minio = make_minio_client()
    counts: dict[str, int] = {}
    async with connection() as conn:
        for table in FK_INSERT_ORDER:
            counts[table] = await _dump_table_to_parquet(conn, table, minio, baseline_id)

    captured_at = datetime.now(UTC).isoformat()
    manifest: dict[str, Any] = {
        "baseline_id": baseline_id,
        "captured_at": captured_at,
        "tables": FK_INSERT_ORDER,
        "row_counts": counts,
        "schema_version": 1,
    }
    payload = json.dumps(manifest, indent=2).encode()
    minio.put_object(
        CATALOG_BUCKET,
        _manifest_key(baseline_id),
        io.BytesIO(payload),
        length=len(payload),
        content_type="application/json",
    )
    return manifest


def _read_manifest(minio: Minio, baseline_id: str) -> dict[str, Any]:
    resp = minio.get_object(CATALOG_BUCKET, _manifest_key(baseline_id))
    try:
        data = resp.read()
    finally:
        resp.close()
        resp.release_conn()
    parsed: dict[str, Any] = json.loads(data)
    return parsed


def _read_table_parquet(minio: Minio, baseline_id: str, table: str) -> list[dict[str, Any]]:
    resp = minio.get_object(CATALOG_BUCKET, _table_key(baseline_id, table))
    try:
        data = resp.read()
    finally:
        resp.close()
        resp.release_conn()
    pa_table = pq.read_table(io.BytesIO(data))
    rows: list[dict[str, Any]] = pa_table.to_pylist()
    return rows


async def _truncate_all_tables(conn: DbConn) -> None:
    """TRUNCATE all 7 tables with CASCADE — handles FK in one statement."""
    tables_sql = ", ".join(FK_INSERT_ORDER)
    await conn.execute(f"TRUNCATE {tables_sql} CASCADE")  # noqa: S608


async def _insert_rows(conn: DbConn, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    cols_sql = ", ".join(columns)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
    sql = f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders})"  # noqa: S608
    for row in rows:
        await conn.execute(sql, *(row[c] for c in columns))


async def restore_baseline(baseline_id: str) -> dict[str, Any]:
    """Truncate every table and re-insert from the named baseline's Parquet.

    Idempotent (NFR-016): re-invoking yields a logically-equivalent state.
    Auto-increment sequences are NOT reset; only non-PK content is guaranteed
    to match.
    """
    minio = make_minio_client()
    try:
        manifest = _read_manifest(minio, baseline_id)
    except S3Error as e:
        if e.code in ("NoSuchKey", "NoSuchObject"):
            raise FileNotFoundError(f"baseline {baseline_id!r} not found") from e
        raise

    restored_counts: dict[str, int] = {}
    async with connection() as conn, conn.transaction():
        await _truncate_all_tables(conn)
        for table in FK_INSERT_ORDER:
            rows = _read_table_parquet(minio, baseline_id, table)
            await _insert_rows(conn, table, rows)
            restored_counts[table] = len(rows)

    return {
        "baseline_id": baseline_id,
        "captured_at": manifest["captured_at"],
        "restored_at": datetime.now(UTC).isoformat(),
        "row_counts": restored_counts,
    }


def list_baselines() -> list[dict[str, Any]]:
    """Return [{baseline_id, captured_at, row_counts}, ...] sorted newest first."""
    minio = make_minio_client()
    objects = minio.list_objects(CATALOG_BUCKET, prefix=f"{BASELINE_PREFIX}/", recursive=True)
    baseline_ids: set[str] = set()
    for obj in objects:
        name = obj.object_name or ""
        if name.endswith(f"/{MANIFEST_NAME}"):
            # Pull baseline_id from "baselines/<id>/manifest.json"
            parts = name.split("/")
            if len(parts) >= 3:
                baseline_ids.add(parts[1])

    entries: list[dict[str, Any]] = []
    for bid in baseline_ids:
        try:
            entries.append(_read_manifest(minio, bid))
        except S3Error:
            continue
    entries.sort(key=lambda m: str(m.get("captured_at", "")), reverse=True)
    return entries


def latest_baseline_id() -> str | None:
    entries = list_baselines()
    return str(entries[0]["baseline_id"]) if entries else None
