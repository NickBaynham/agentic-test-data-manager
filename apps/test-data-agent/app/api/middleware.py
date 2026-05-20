"""API token middleware.

Per BRD §16 decision #3 (NFR-004): mutating endpoints require
`Authorization: Bearer ${ATDM_API_TOKEN}`. Read endpoints are open on the
local network. Health and metrics are always open.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

# Methods that mutate state. GET / HEAD / OPTIONS pass through.
_MUTATING_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Paths that bypass auth even when they use mutating methods (rare).
_BYPASS_PATHS: frozenset[str] = frozenset({"/health", "/metrics"})


def _expected_token() -> str:
    return os.environ.get("ATDM_API_TOKEN", "dev-token-change-me")


async def api_token_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[JSONResponse]],
) -> JSONResponse:
    if request.method not in _MUTATING_METHODS or request.url.path in _BYPASS_PATHS:
        return await call_next(request)

    header = request.headers.get("authorization", "")
    expected = f"Bearer {_expected_token()}"
    if header != expected:
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "AUTH_REQUIRED",
                    "message": "Mutating endpoints require a Bearer token "
                    "in the Authorization header.",
                }
            },
        )
    return await call_next(request)
