"""Binary sensor platform for Reef Dose — whether a calibration run is
in progress.

Exists specifically to drive a guided Lovelace flow: a `conditional`
card keyed on this entity can show "Start Calibration" while it's off
and swap in "Calibration Measured Amount" + "Apply Calibration" once
it's on, instead of always showing all three at once - see README for
the worked dashboard YAML. Backed by coordinator.calibration_sessions
(button.py's Start/Apply buttons set/clear it), not polled from the
device - there's no device-side "is a run in progress" flag to read.
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ReefDoseCoordinator


class ReefDoseCalibratingBinarySensor(CoordinatorEntity[ReefDoseCoordinator], BinarySensorEntity):
    """On between Start Calibration and Apply Calibration for one pump."""

    _attr_has_entity_name = True
    _attr_name = "Calibrating"

    def __init__(self, coordinator: ReefDoseCoordinator, pump_id: str) -> None:
        super().__init__(coordinator)
        self._pump_id = pump_id
        self._attr_unique_id = f"{pump_id}_calibrating"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pump_id)},
            name=f"Pump {pump_id}",
            manufacturer="Reef Dose",
            model="Pump",
        )

    @property
    def is_on(self) -> bool:
        return self._pump_id in self.coordinator.calibration_sessions


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id].coordinator

    # Dosed-pump-only, same restriction as calibration's buttons/number
    # in button.py/number.py.
    async_add_entities(
        ReefDoseCalibratingBinarySensor(coordinator, pump_id)
        for pump_id, pump in coordinator.data.items()
        if pump.get("scheduleEnabled") is not None
    )
