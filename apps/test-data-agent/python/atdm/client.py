"""Synchronous HTTP client for the ATDM agent.

Reads `ATDM_API_URL` and `ATDM_API_TOKEN` from the environment. Each method
returns the JSON response as a dict (or list, where the endpoint returns one).
On HTTP errors, raises `AtdmClientError` with the status and body.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class AtdmClientError(Exception):
    """Raised on any non-2xx response from the agent."""

    def __init__(self, message: str, *, status_code: int, body: Any) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _env_url() -> str:
    return os.environ.get("ATDM_API_URL", "http://localhost:18001")


def _env_token() -> str:
    return os.environ.get("ATDM_API_TOKEN", "dev-token-change-me")


class AtdmClient:
    """Thin sync wrapper over the ATDM agent's HTTP API.

    Auth header is attached automatically to every mutating call.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url or _env_url()
        self._token = token or _env_token()
        self._timeout = timeout

    # -------------------------------------------------------------------
    # Internals
    # -------------------------------------------------------------------

    def _headers(self, *, auth: bool, extra: dict[str, str] | None = None) -> dict[str, str]:
        h: dict[str, str] = {}
        if auth:
            h["authorization"] = f"Bearer {self._token}"
        if extra:
            h.update(extra)
        return h

    def _call(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        auth: bool,
        headers: dict[str, str] | None = None,
    ) -> Any:
        with httpx.Client(base_url=self._base_url, timeout=self._timeout) as c:
            resp = c.request(
                method,
                path,
                json=json,
                headers=self._headers(auth=auth, extra=headers),
            )
        if resp.status_code >= 400:
            try:
                body: Any = resp.json()
            except Exception:  # noqa: BLE001
                body = resp.text
            raise AtdmClientError(
                f"{method} {path} returned {resp.status_code}",
                status_code=resp.status_code,
                body=body,
            )
        if not resp.content:
            return None
        return resp.json()

    # -------------------------------------------------------------------
    # Scenario request lifecycle
    # -------------------------------------------------------------------

    def request_scenario(
        self,
        scenario: str,
        *,
        constraints: dict[str, Any] | None = None,
        return_playwright_fixture: bool = False,
        return_pytest_fixture: bool = False,
        domain: str = "healthcare",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "domain": domain,
            "scenario": scenario,
            "constraints": constraints or {},
            "delivery": {
                "seed_target": True,
                "return_playwright_fixture": return_playwright_fixture,
                "return_pytest_fixture": return_pytest_fixture,
            },
        }
        result: dict[str, Any] = self._call("POST", "/test-data/requests", json=body, auth=True)
        return result

    def reset_run(self, run_id: str, cleanup_token: str) -> dict[str, Any]:
        result: dict[str, Any] = self._call(
            "POST",
            f"/test-data/runs/{run_id}/reset",
            json={"cleanup_token": cleanup_token},
            auth=True,
        )
        return result

    # -------------------------------------------------------------------
    # Strategy endpoints
    # -------------------------------------------------------------------

    def reset_all(self) -> dict[str, Any]:
        result: dict[str, Any] = self._call(
            "POST",
            "/test-data/reset/all",
            auth=True,
            headers={"X-Confirm": "yes"},
        )
        return result

    def baseline_snapshot(self, baseline_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"baseline_id": baseline_id} if baseline_id else {}
        result: dict[str, Any] = self._call(
            "POST", "/test-data/baseline/snapshot", json=body, auth=True
        )
        return result

    def baseline_restore(self, baseline_id: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"baseline_id": baseline_id} if baseline_id else {}
        result: dict[str, Any] = self._call(
            "POST", "/test-data/baseline/restore", json=body, auth=True
        )
        return result

    def baseline_list(self) -> dict[str, Any]:
        result: dict[str, Any] = self._call("GET", "/test-data/baseline/list", auth=False)
        return result

    # -------------------------------------------------------------------
    # Read endpoints
    # -------------------------------------------------------------------

    def get_audit(self, run_id: str) -> dict[str, Any]:
        result: dict[str, Any] = self._call("GET", f"/audit/runs/{run_id}", auth=False)
        return result

    def get_scenarios(self) -> dict[str, Any]:
        result: dict[str, Any] = self._call("GET", "/catalog/scenarios", auth=False)
        return result
