"""Coordinator: polls reef-dose-service for every pump's name + schedule."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ReefDoseApiError, ReefDoseAuthError, ReefDoseClient
from .const import DEFAULT_UPDATE_INTERVAL_MINUTES, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ReefDoseCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetches every pump's name + schedule, keyed by pump id."""

    def __init__(self, hass: HomeAssistant, client: ReefDoseClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL_MINUTES),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            pump_ids = await self.client.async_get_pump_ids()
        except ReefDoseAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except ReefDoseApiError as err:
            raise UpdateFailed(f"Error communicating with reef-dose-service: {err}") from err

        data: dict[str, dict[str, Any]] = {}
        for pump_id in pump_ids:
            try:
                name = await self.client.async_get_name(pump_id)
            except ReefDoseAuthError as err:
                raise UpdateFailed(f"Authentication failed: {err}") from err
            except ReefDoseApiError as err:
                raise UpdateFailed(f"Error communicating with reef-dose-service: {err}") from err

            pump_data: dict[str, Any] = {"name": name}
            try:
                pump_data.update(await self.client.async_get_schedule(pump_id))
            except ReefDoseAuthError as err:
                raise UpdateFailed(f"Authentication failed: {err}") from err
            except ReefDoseApiError:
                # Not every pump has a product assigned (schedule-capable) -
                # the service's own PumpsService.requireDosedPump rejects
                # the rest with a 400. Still expose the name/prime button
                # for those, just without schedule-dependent entities.
                pump_data["scheduleEnabled"] = None
                pump_data["splitDoseEnabled"] = None

            data[pump_id] = pump_data

        return data
