"""Target Healthcare API — Phase 1 stub.

Serves as the System Under Test for ATDM. Real entity routes (Member, Plan,
Provider, Eligibility, Claim, ProcedureCode, DiagnosisCode) land in Phase 2.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Target Healthcare API",
    description="Synthetic healthcare SUT for the Agentic Test Data Manager.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by docker compose healthcheck and integration tests."""
    return {"status": "ok", "service": "target-healthcare-api"}
