"""The Reef Dose integration."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ReefDoseClient
from .const import CONF_API_KEY, CONF_HOST, DOMAIN
from .coordinator import ReefDoseCoordinator
from .groups_coordinator import ReefDoseGroupsCoordinator

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.BUTTON, Platform.SENSOR, Platform.NUMBER]


@dataclass
class ReefDoseData:
    """Everything a platform's async_setup_entry needs from hass.data."""

    coordinator: ReefDoseCoordinator
    groups_coordinator: ReefDoseGroupsCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = ReefDoseClient(session, entry.data[CONF_HOST], entry.data[CONF_API_KEY])

    coordinator = ReefDoseCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    groups_coordinator = ReefDoseGroupsCoordinator(hass, client)
    await groups_coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = ReefDoseData(coordinator, groups_coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
