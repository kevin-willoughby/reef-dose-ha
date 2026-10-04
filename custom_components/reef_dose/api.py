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

    async def async_manual_dose(self, pump_id: str, ml: float) -> None:
        await self._request("POST", f"/pumps/{pump_id}/dose", json={"ml": ml})

    async def async_start_calibration(self, pump_id: str) -> int:
        """Start a calibration run; returns the sessionId to pass to apply."""
        body = await self._request("POST", f"/pumps/{pump_id}/calibration/start")
        return body["sessionId"]

    async def async_apply_calibration(
        self, pump_id: str, session_id: int, measured_ml: float
    ) -> None:
        await self._request(
            "POST",
            f"/pumps/{pump_id}/calibration/apply",
            json={"sessionId": session_id, "measuredMl": measured_ml},
        )

    async def async_get_reservoir(self, pump_id: str) -> dict[str, Any]:
        """Return {pumpId, remainingMl, fullMl, daysRemaining}."""
        return await self._request("GET", f"/pumps/{pump_id}/reservoir")

    async def async_refill_reservoir(self, pump_id: str) -> None:
        await self._request("POST", f"/pumps/{pump_id}/reservoir/refill")

    async def async_auto_divide_schedule(self, pump_id: str, daily_total_ml: float) -> dict[str, Any]:
        """Evenly split daily_total_ml across all 24 hourly slots; returns the resulting schedule."""
        return await self._request(
            "POST", f"/pumps/{pump_id}/schedule/auto-divide", json={"dailyTotalMl": daily_total_ml}
        )

    async def async_get_groups(self) -> list[dict[str, Any]]:
        """Return every scaling group as [{id, name, pumpIds, scalePercent}, ...]."""
        return await self._request("GET", "/groups")

    async def async_update_group(self, group_id: str, **fields: Any) -> dict[str, Any]:
        """Partial update - only pass the fields that changed, e.g.
        async_update_group(group_id, scalePercent=110).
        """
        return await self._request("PATCH", f"/groups/{group_id}", json=fields)

    async def async_create_group(
        self,
        group_id: str,
        name: str,
        pump_ids: list[str],
        scale_percent: float | None = None,
        auto_sync: bool | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name, "pumpIds": pump_ids}
        if scale_percent is not None:
            body["scalePercent"] = scale_percent
        if auto_sync is not None:
            body["autoSync"] = auto_sync
        return await self._request("POST", f"/groups/{group_id}", json=body)

    async def async_delete_group(self, group_id: str) -> None:
        await self._request("DELETE", f"/groups/{group_id}")

    async def async_sync_group_member(self, group_id: str, pump_id: str) -> None:
        """Pushes the group's current template to just this one member."""
        await self._request("POST", f"/groups/{group_id}/sync/{pump_id}")

    async def async_sync_group(self, group_id: str) -> None:
        """Pushes the group's current template to every current member."""
        await self._request("POST", f"/groups/{group_id}/sync")

    async def async_get_group_schedule(self, group_id: str) -> dict[str, Any]:
        """Return {id, scalePercent, slots} - the group's own canonical schedule."""
        return await self._request("GET", f"/groups/{group_id}/schedule")

    async def async_update_group_schedule(self, group_id: str, slots: dict[str, float]) -> dict[str, Any]:
        return await self._request("PATCH", f"/groups/{group_id}/schedule", json={"slots": slots})

    async def async_auto_divide_group_schedule(self, group_id: str, daily_total_ml: float) -> dict[str, Any]:
        return await self._request(
            "POST", f"/groups/{group_id}/schedule/auto-divide", json={"dailyTotalMl": daily_total_ml}
        )

    async def async_apply_pump_adjustment(self, pump_id: str, delta_percent: float) -> dict[str, Any]:
        """Section 5's "Manual Overall Adjustment" for a single, ungrouped pump."""
        return await self._request(
            "POST", f"/pumps/{pump_id}/adjustment", json={"deltaPercent": delta_percent}
        )

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
