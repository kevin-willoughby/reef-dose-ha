"""Coordinator: polls reef-dose-service for every scaling group.

Separate from ReefDoseCoordinator (pump-keyed) since a group record
has a different shape (name, pumpIds, scalePercent) and a different
identity space (group id, not physical pump number) - mixing the two
into one dict would break every existing pump-keyed entity's
assumption that coordinator.data[pump_id] is a pump record.

Groups are genuinely dynamic (created/deleted via the API, not a
fixed set of 6 like pumps) - see groups.service.ts in reef-dose-
service. Entities are still only created once, from whatever groups
exist at integration setup (number.py's async_setup_entry) - a group
created later via the API needs a reload of this integration to show
up as an entity. Documented in README.md rather than solved with
dynamic entity discovery, since group creation is a rare, deliberate
setup action, not something that needs to appear live.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ReefDoseApiError, ReefDoseAuthError, ReefDoseClient
from .const import DEFAULT_UPDATE_INTERVAL_MINUTES, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ReefDoseGroupsCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetches every scaling group, keyed by group id."""

    def __init__(self, hass: HomeAssistant, client: ReefDoseClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_groups",
            update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL_MINUTES),
        )
        self.client = client

        # Pending "Manual Overall Adjustment" delta (%) per group, not
        # polled - see number.py's ReefDoseGroupAdjustmentNumber /
        # button.py's ReefDoseApplyGroupAdjustmentButton. Reset to 0
        # after each Apply.
        self.pending_adjustment: dict[str, float] = {}

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            groups = await self.client.async_get_groups()
        except ReefDoseAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except ReefDoseApiError as err:
            raise UpdateFailed(f"Error communicating with reef-dose-service: {err}") from err

        return {group["id"]: group for group in groups}
