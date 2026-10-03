"""Sensor platform for Reef Dose — the pump's current product label.

Split out from the device name deliberately (see switch.py's
ReefDoseSwitch) so renaming a pump's product live doesn't leave HA's
device name stale - this sensor just tracks whatever the coordinator's
next poll sees, same as every other coordinator-backed entity here.
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ReefDoseCoordinator


class ReefDoseLabelSensor(CoordinatorEntity[ReefDoseCoordinator], SensorEntity):
    """The pump's current OLED display label / product name."""

    _attr_has_entity_name = True
    _attr_name = "Label"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ReefDoseCoordinator, pump_id: str) -> None:
        super().__init__(coordinator)
        self._pump_id = pump_id
        self._attr_unique_id = f"{pump_id}_label"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pump_id)},
            name=f"Pump {pump_id}",
            manufacturer="Reef Dose",
            model="Pump",
        )

    @property
    def native_value(self) -> str | None:
        pump = self.coordinator.data.get(self._pump_id)
        return pump["name"] if pump else None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ReefDoseCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        ReefDoseLabelSensor(coordinator, pump_id) for pump_id in coordinator.data
    )
