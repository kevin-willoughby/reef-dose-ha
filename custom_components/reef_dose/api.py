"""Thin async client for reef-dose-service's REST API.

Every request carries the api key in X-Api-Key — reef-dose-service's
ApiKeyGuard rejects anything else with a plain 401, no body worth
parsing, so auth failures are detected by status code alone.
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class ReefDoseAuthError(Exception):
    """Raised when the service rejects our api key (401)."""


class ReefDoseApiError(Exception):
    """Raised for any other API failure."""


class ReefDoseClient:
    """Handles requests to one reef-dose-service instance."""

    def __init__(self, session: aiohttp.ClientSession, host: str, api_key: str) -> None:
        self._session = session
        self._base_url = f"http://{host}"
        self._headers = {"x-api-key": api_key}

    async def async_get_pump_ids(self) -> list[str]:
        """Return every pump id the service knows about (1-6, physical pump number)."""
        return await self._request("GET", "/pumps")

    async def async_get_name(self, pump_id: str) -> str:
        body = await self._request("GET", f"/pumps/{pump_id}/name")
        return body["name"]

    async def async_set_name(self, pump_id: str, name: str) -> str:
        body = await self._request("PATCH", f"/pumps/{pump_id}/name", json={"name": name})
        return body["name"]

    async def async_prime(self, pump_id: str) -> None:
        await self._request("POST", f"/pumps/{pump_id}/prime")

    async def async_get_schedule(self, pump_id: str) -> dict[str, Any]:
        """Return {pumpId, scheduleEnabled, slots, splitDoseEnabled}."""
        return await self._request("GET", f"/pumps/{pump_id}/schedule")

    async def async_update_schedule(self, pump_id: str, **fields: Any) -> dict[str, Any]:
        """Partial update - only pass the fields that changed, e.g.
        async_update_schedule(pump_id, scheduleEnabled=True).
        """
        return await self._request("PATCH", f"/pumps/{pump_id}/schedule", json=fields)

    async def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> Any:
        try:
            async with self._session.request(
                method, f"{self._base_url}{path}", headers=self._headers, json=json
            ) as resp:
                if resp.status == 401:
                    raise ReefDoseAuthError("reef-dose-service rejected the api key")
                if resp.status >= 400:
                    text = await resp.text()
                    raise ReefDoseApiError(f"{method} {path} failed: HTTP {resp.status}: {text}")
                if resp.status == 204 or resp.content_length == 0:
                    return None
                return await resp.json()
        except aiohttp.ClientError as err:
            raise ReefDoseApiError(f"{method} {path} failed: {err}") from err
