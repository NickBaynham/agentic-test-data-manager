"""ProcedureCode and DiagnosisCode repositories.

Reference tables: baseline rows have `test_run_id IS NULL` and are shared
across runs (inserted by the migration). Per-run "invalid" variants carry the
run's test_run_id and are deleted with the run.

Inserts use ON CONFLICT (code) DO NOTHING — if a baseline code already exists,
we don't trample it. This means scenarios may reference baseline codes
directly without inserting their own; they only insert when adding a per-run
"invalid" variant that didn't exist before.
"""

from __future__ import annotations

from app.db.session import DbConn, connection
from app.models.codes import DiagnosisCode, ProcedureCode

_INSERT_PROC = """
    INSERT INTO procedure_code (code, description, is_valid, test_run_id)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (code) DO NOTHING
"""
_INSERT_DIAG = """
    INSERT INTO diagnosis_code (code, description, is_valid, test_run_id)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (code) DO NOTHING
"""
# Only delete rows we own (test_run_id IS NOT NULL and matches).
_DELETE_PROC_BY_RUN = "DELETE FROM procedure_code WHERE test_run_id = $1"
_DELETE_DIAG_BY_RUN = "DELETE FROM diagnosis_code WHERE test_run_id = $1"


async def insert_procedure_code(
    code: ProcedureCode,
    *,
    conn: DbConn | None = None,
) -> None:
    args = (code.code, code.description, code.is_valid, code.test_run_id)
    if conn is not None:
        await conn.execute(_INSERT_PROC, *args)
        return
    async with connection() as c:
        await c.execute(_INSERT_PROC, *args)


async def insert_diagnosis_code(
    code: DiagnosisCode,
    *,
    conn: DbConn | None = None,
) -> None:
    args = (code.code, code.description, code.is_valid, code.test_run_id)
    if conn is not None:
        await conn.execute(_INSERT_DIAG, *args)
        return
    async with connection() as c:
        await c.execute(_INSERT_DIAG, *args)


async def delete_procedure_codes_by_run(run_id: str, *, conn: DbConn | None = None) -> int:
    if conn is not None:
        result = await conn.execute(_DELETE_PROC_BY_RUN, run_id)
    else:
        async with connection() as c:
            result = await c.execute(_DELETE_PROC_BY_RUN, run_id)
    parts = result.split()
    return int(parts[1]) if len(parts) == 2 and parts[0] == "DELETE" else 0


async def delete_diagnosis_codes_by_run(run_id: str, *, conn: DbConn | None = None) -> int:
    if conn is not None:
        result = await conn.execute(_DELETE_DIAG_BY_RUN, run_id)
    else:
        async with connection() as c:
            result = await c.execute(_DELETE_DIAG_BY_RUN, run_id)
    parts = result.split()
    return int(parts[1]) if len(parts) == 2 and parts[0] == "DELETE" else 0
