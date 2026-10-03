"""Switch platform for Reef Dose — per-pump schedule-enabled and split-dose.

One description per switch, same idiom as Alkatronic's sensor.py - adding
another schedule-backed boolean later is just another description.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ReefDoseCoordinator


@dataclass(frozen=True, kw_only=True)
class ReefDoseSwitchDescription(SwitchEntityDescription):
    field: str = ""  # key in the coordinator's per-pump schedule dict


SWITCH_DESCRIPTIONS: tuple[ReefDoseSwitchDescription, ...] = (
    ReefDoseSwitchDescription(
        key="schedule_enabled", name="Schedule Enabled", field="scheduleEnabled"
    ),
    ReefDoseSwitchDescription(
        key="split_dose_enabled",
        name="Split Dose (2x Per Hour)",
        field="splitDoseEnabled",
    ),
)


class ReefDoseSwitch(CoordinatorEntity[ReefDoseCoordinator], SwitchEntity):
    """One schedule-backed boolean for one pump."""

    entity_description: ReefDoseSwitchDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ReefDoseCoordinator,
        description: ReefDoseSwitchDescription,
        pump_id: str,
        device_name: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._pump_id = pump_id
        self._attr_unique_id = f"{pump_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pump_id)},
            name=device_name,
            manufacturer="Reef Dose",
            model="Pump",
        )

    @property
    def is_on(self) -> bool | None:
        pump = self.coordinator.data.get(self._pump_id)
        if pump is None:
            return None
        return pump.get(self.entity_description.field)

    @property
    def available(self) -> bool:
        return super().available and self.is_on is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)

    async def _async_set(self, value: bool) -> None:
        await self.coordinator.client.async_update_schedule(
            self._pump_id, **{self.entity_description.field: value}
        )
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ReefDoseCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[ReefDoseSwitch] = []
    for pump_id, pump in coordinator.data.items():
        # scheduleEnabled is None for a pump with no product assigned
        # (not schedule-capable) - see coordinator.py.
        if pump.get("scheduleEnabled") is None:
            continue
        for description in SWITCH_DESCRIPTIONS:
            entities.append(
                ReefDoseSwitch(coordinator, description, pump_id, pump["name"])
            )

    async_add_entities(entities)
