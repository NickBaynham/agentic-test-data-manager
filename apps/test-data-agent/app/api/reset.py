"""POST /test-data/runs/{run_id}/reset — cleanup-token-gated reset_run.

Verifies cleanup_token against the stored sha256 hash in the catalog. On
match, deletes Member then Plan by run_id via the Target SUT and updates the
catalog status. Idempotent: a second call returns `already_cleaned`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.audit import writer as audit_writer
from app.catalog import store as catalog_store
from app.seeders import healthcare as seeder

router = APIRouter()


class ResetRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    cleanup_token: str = Field(min_length=1)


def _invoker_from(request: Request) -> str:
    return "agent:atdm-dev"


@router.post("/test-data/runs/{run_id}/reset")
async def reset_run(run_id: str, body: ResetRequest, request: Request) -> dict[str, object]:
    minio_client = catalog_store.make_minio_client()

    entry = catalog_store.read_run(minio_client, run_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "RUN_NOT_FOUND",
                    "message": f"no catalog entry for run_id {run_id!r}",
                }
            },
        )

    expected_hash = entry["cleanup_token_sha256"]
    if catalog_store.sha256_token(body.cleanup_token) != expected_hash:
        # Per FR-035, never reveal which run_ids exist with what tokens.
        # Log this attempt in the audit log for forensics.
        audit_writer.append_event(
            minio_client,
            test_run_id=run_id,
            invoker=_invoker_from(request),
            action="reset_rejected",
            outputs={"reason": "token_mismatch"},
            status="forbidden",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "TOKEN_MISMATCH",
                    "message": "cleanup_token does not match",
                }
            },
        )

    current_status = entry["status"]
    if current_status == "cleaned":
        return {"run_id": run_id, "status": "already_cleaned"}

    audit_writer.append_event(
        minio_client,
        test_run_id=run_id,
        invoker=_invoker_from(request),
        action="reset_started",
        inputs={"strategy": "reset_run"},
    )

    counts = await seeder.reset_run(run_id)
    catalog_store.update_status(minio_client, run_id, "cleaned")

    audit_writer.append_event(
        minio_client,
        test_run_id=run_id,
        invoker=_invoker_from(request),
        action="reset_completed",
        outputs={"strategy": "reset_run", "deleted_counts": counts},
        status="cleaned",
    )

    return {"run_id": run_id, "status": "cleaned", "deleted_counts": counts}
