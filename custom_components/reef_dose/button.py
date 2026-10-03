"""Button platform for Reef Dose — fire a pump's prime pulse.

Every pump gets one, dosed or not (priming doesn't need a product
assigned), unlike the schedule-backed switches in switch.py.
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ReefDoseCoordinator


class ReefDosePrimeButton(ButtonEntity):
    """Fires a 10s prime pulse on one pump."""

    _attr_has_entity_name = True
    _attr_name = "Prime"

    def __init__(self, coordinator: ReefDoseCoordinator, pump_id: str) -> None:
        self._coordinator = coordinator
        self._pump_id = pump_id
        self._attr_unique_id = f"{pump_id}_prime"
        # See switch.py's ReefDoseSwitch for why this is the fixed pump
        # number, not the current (renameable) product label.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pump_id)},
            name=f"Pump {pump_id}",
            manufacturer="Reef Dose",
            model="Pump",
        )

    async def async_press(self) -> None:
        await self._coordinator.client.async_prime(self._pump_id)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ReefDoseCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        ReefDosePrimeButton(coordinator, pump_id) for pump_id in coordinator.data
    )
