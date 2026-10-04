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

        # Plain local state, not polled - holds the per-pump number-entity
        # values and in-flight calibration session ids so the matching
        # button (manual dose / apply calibration) can read them at press
        # time without a cross-platform entity lookup. See number.py.
        self.manual_dose_ml: dict[str, float] = {}
        self.calibration_measured_ml: dict[str, float] = {}
        self.calibration_sessions: dict[str, int] = {}
        # Pending "total ml/day" for the Auto-Divide Schedule button -
        # see button.py's ReefDoseAutoDivideButton / number.py's
        # ReefDoseDailyTotalMlNumber.
        self.daily_total_ml: dict[str, float] = {}

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

            # Reservoir is the same dosed-pump-only restriction as schedule
            # above (requireDosedPump) - only bother asking when schedule
            # succeeded, rather than making a second doomed request.
            if pump_data["scheduleEnabled"] is not None:
                try:
                    pump_data.update(await self.client.async_get_reservoir(pump_id))
                except ReefDoseAuthError as err:
                    raise UpdateFailed(f"Authentication failed: {err}") from err
                except ReefDoseApiError:
                    pump_data["remainingMl"] = None
                    pump_data["fullMl"] = None
                    pump_data["daysRemaining"] = None
            else:
                pump_data["remainingMl"] = None
                pump_data["fullMl"] = None
                pump_data["daysRemaining"] = None

            data[pump_id] = pump_data

        return data
