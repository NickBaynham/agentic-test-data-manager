"""Phase 5 reset strategies — agent-side endpoints.

  POST /test-data/reset/all              (X-Confirm: yes required)
  POST /test-data/baseline/snapshot      (optional baseline_id body field)
  POST /test-data/baseline/restore       (optional baseline_id body field)
  GET  /test-data/baseline/list

`reset_run` (per-run cleanup-token-gated) is in api/reset.py from Phase 3.
These four are the remaining strategies. Each emits audit events under a
synthetic run_id (`strategy:<name>:<timestamp>`) so they appear in the audit
trail alongside scenario requests.
"""

from __future__ import annotations

import os
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from ulid import ULID

from app.audit import writer as audit_writer
from app.catalog import store as catalog_store

router = APIRouter()


def _sut_base_url() -> str:
    return os.environ.get("TARGET_SUT_URL", "http://target-healthcare-api:8000")


def _invoker_from(_request: Request) -> str:
    return "agent:atdm-dev"


def _strategy_run_id(strategy: str) -> str:
    """Generate a synthetic run_id so strategy events get their own audit trail."""
    return f"strategy-{strategy}-{ULID()}"


# ---------------------------------------------------------------------------
# reset_all — requires X-Confirm: yes header
# ---------------------------------------------------------------------------


@router.post("/test-data/reset/all")
async def reset_all(
    request: Request,
    x_confirm: str | None = Header(default=None, alias="X-Confirm"),
) -> dict[str, Any]:
    if x_confirm != "yes":
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={
                "error": {
                    "code": "CONFIRM_REQUIRED",
                    "message": "POST /test-data/reset/all requires header 'X-Confirm: yes'. "
                    "This endpoint clears every test_run_id-tagged row across all "
                    "mutable tables.",
                }
            },
        )

    run_id = _strategy_run_id("reset_all")
    invoker = _invoker_from(request)
    minio_client = catalog_store.make_minio_client()

    audit_writer.append_event(
        minio_client,
        test_run_id=run_id,
        invoker=invoker,
        action="reset_started",
        inputs={"strategy": "reset_all"},
    )

    try:
        async with httpx.AsyncClient(base_url=_sut_base_url(), timeout=15.0) as client:
            resp = await client.post("/internal/reset/all-tagged")
    except httpx.HTTPError as e:
        audit_writer.append_event(
            minio_client,
            test_run_id=run_id,
            invoker=invoker,
            action="reset_failed",
            outputs={"strategy": "reset_all", "message": str(e)},
            status="failed",
        )
        raise HTTPException(status_code=502, detail={"error": {"code": "SUT_UNREACHABLE"}}) from e

    if resp.status_code != 200:
        audit_writer.append_event(
            minio_client,
            test_run_id=run_id,
            invoker=invoker,
            action="reset_failed",
            outputs={"strategy": "reset_all", "downstream_status": resp.status_code},
            status="failed",
        )
        raise HTTPException(status_code=502, detail={"error": {"code": "RESET_FAILED"}})

    body = resp.json()
    cleared = sum(body.get("deleted_counts", {}).values())
    audit_writer.append_event(
        minio_client,
        test_run_id=run_id,
        invoker=invoker,
        action="reset_completed",
        outputs={
            "strategy": "reset_all",
            "deleted_counts": body["deleted_counts"],
            "cleared_record_count": cleared,
        },
        status="cleaned",
    )

    return {
        "strategy": "reset_all",
        "audit_run_id": run_id,
        "deleted_counts": body["deleted_counts"],
        "cleared_record_count": cleared,
    }


# ---------------------------------------------------------------------------
# baseline snapshot / restore / list
# ---------------------------------------------------------------------------


class BaselineSnapshotRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    baseline_id: str | None = Field(default=None)


@router.post("/test-data/baseline/snapshot")
async def baseline_snapshot(body: BaselineSnapshotRequest, request: Request) -> dict[str, Any]:
    bid = body.baseline_id or (
        f"bl-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    )
    run_id = _strategy_run_id("baseline_snapshot")
    invoker = _invoker_from(request)
    minio_client = catalog_store.make_minio_client()

    audit_writer.append_event(
        minio_client,
        test_run_id=run_id,
        invoker=invoker,
        action="snapshot_started",
        inputs={"strategy": "baseline_snapshot", "baseline_id": bid},
    )

    try:
        async with httpx.AsyncClient(base_url=_sut_base_url(), timeout=60.0) as client:
            resp = await client.post("/internal/baseline/snapshot", params={"baseline_id": bid})
    except httpx.HTTPError as e:
        audit_writer.append_event(
            minio_client,
            test_run_id=run_id,
            invoker=invoker,
            action="snapshot_failed",
            outputs={"message": str(e)},
            status="failed",
        )
        raise HTTPException(status_code=502, detail={"error": {"code": "SUT_UNREACHABLE"}}) from e

    if resp.status_code not in (200, 201):
        audit_writer.append_event(
            minio_client,
            test_run_id=run_id,
            invoker=invoker,
            action="snapshot_failed",
            outputs={"downstream_status": resp.status_code, "body": resp.text},
            status="failed",
        )
        raise HTTPException(status_code=502, detail={"error": {"code": "SNAPSHOT_FAILED"}})

    manifest = resp.json()
    audit_writer.append_event(
        minio_client,
        test_run_id=run_id,
        invoker=invoker,
        action="snapshot_completed",
        outputs={"manifest": manifest},
        status="ok",
    )
    return {"strategy": "baseline_snapshot", "audit_run_id": run_id, **manifest}


class BaselineRestoreRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    baseline_id: str | None = Field(default=None)


@router.post("/test-data/baseline/restore")
async def baseline_restore(body: BaselineRestoreRequest, request: Request) -> dict[str, Any]:
    run_id = _strategy_run_id("baseline_restore")
    invoker = _invoker_from(request)
    minio_client = catalog_store.make_minio_client()

    audit_writer.append_event(
        minio_client,
        test_run_id=run_id,
        invoker=invoker,
        action="restore_started",
        inputs={"strategy": "baseline_restore", "baseline_id": body.baseline_id},
    )

    params = {"baseline_id": body.baseline_id} if body.baseline_id else {}
    try:
        async with httpx.AsyncClient(base_url=_sut_base_url(), timeout=60.0) as client:
            resp = await client.post("/internal/baseline/restore", params=params)
    except httpx.HTTPError as e:
        audit_writer.append_event(
            minio_client,
            test_run_id=run_id,
            invoker=invoker,
            action="restore_failed",
            outputs={"message": str(e)},
            status="failed",
        )
        raise HTTPException(status_code=502, detail={"error": {"code": "SUT_UNREACHABLE"}}) from e

    if resp.status_code == 404:
        audit_writer.append_event(
            minio_client,
            test_run_id=run_id,
            invoker=invoker,
            action="restore_failed",
            outputs={"reason": "no_baseline"},
            status="failed",
        )
        raise HTTPException(status_code=404, detail=resp.json().get("detail", {}))

    if resp.status_code != 200:
        audit_writer.append_event(
            minio_client,
            test_run_id=run_id,
            invoker=invoker,
            action="restore_failed",
            outputs={"downstream_status": resp.status_code, "body": resp.text},
            status="failed",
        )
        raise HTTPException(status_code=502, detail={"error": {"code": "RESTORE_FAILED"}})

    result = resp.json()
    audit_writer.append_event(
        minio_client,
        test_run_id=run_id,
        invoker=invoker,
        action="restore_completed",
        outputs={"result": result},
        status="ok",
    )
    return {"strategy": "baseline_restore", "audit_run_id": run_id, **result}


@router.get("/test-data/baseline/list")
async def baseline_list() -> dict[str, Any]:
    """Read-only — no auth, no audit event."""
    try:
        async with httpx.AsyncClient(base_url=_sut_base_url(), timeout=10.0) as client:
            resp = await client.get("/internal/baseline/list")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail={"error": {"code": "SUT_UNREACHABLE"}}) from e
    body: dict[str, Any] = resp.json()
    return body


# Suppress an unused-import linter complaint while keeping `secrets` available
# for future use (token generation for new strategies).
_ = secrets
