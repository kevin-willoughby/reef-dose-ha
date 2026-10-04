"""Sensor platform for Reef Dose — the pump's current product label.

Split out from the device name deliberately (see switch.py's
ReefDoseSwitch) so renaming a pump's product live doesn't leave HA's
device name stale - this sensor just tracks whatever the coordinator's
next poll sees, same as every other coordinator-backed entity here.
"""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ReefDoseCoordinator
from .groups_coordinator import ReefDoseGroupsCoordinator


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


@dataclass(frozen=True, kw_only=True)
class ReefDoseReservoirSensorDescription(SensorEntityDescription):
    field: str = ""  # key in the coordinator's per-pump dict (see coordinator.py)


RESERVOIR_SENSOR_DESCRIPTIONS: tuple[ReefDoseReservoirSensorDescription, ...] = (
    ReefDoseReservoirSensorDescription(
        key="reservoir_remaining",
        name="Reservoir Remaining",
        field="remainingMl",
        native_unit_of_measurement="mL",
    ),
    ReefDoseReservoirSensorDescription(
        key="reservoir_full",
        name="Reservoir Full Volume",
        field="fullMl",
        native_unit_of_measurement="mL",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Projected from the pump's CURRENT schedule total, not historical
    # usage - see reef-dose-service's PumpsService.getReservoir. None
    # (unknown) when the schedule is off or every slot is 0ml, not a
    # misleading number.
    ReefDoseReservoirSensorDescription(
        key="reservoir_days_remaining",
        name="Reservoir Days Remaining",
        field="daysRemaining",
        native_unit_of_measurement="d",
    ),
)


class ReefDoseReservoirSensor(CoordinatorEntity[ReefDoseCoordinator], SensorEntity):
    """One reservoir-derived numeric reading for one pump."""

    entity_description: ReefDoseReservoirSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ReefDoseCoordinator,
        description: ReefDoseReservoirSensorDescription,
        pump_id: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._pump_id = pump_id
        self._attr_unique_id = f"{pump_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pump_id)},
            name=f"Pump {pump_id}",
            manufacturer="Reef Dose",
            model="Pump",
        )

    @property
    def native_value(self) -> float | None:
        pump = self.coordinator.data.get(self._pump_id)
        if pump is None:
            return None
        return pump.get(self.entity_description.field)


class ReefDoseGroupScaleSensor(CoordinatorEntity[ReefDoseGroupsCoordinator], SensorEntity):
    """Read-only current absolute scale for one group (requirements.md
    Section 5) - the value number.py's Manual Overall Adjustment
    deltas actually compound onto. 100 is the group's unscaled base.
    """

    _attr_has_entity_name = True
    _attr_name = "Current Scale"
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator: ReefDoseGroupsCoordinator, group_id: str) -> None:
        super().__init__(coordinator)
        self._group_id = group_id
        self._attr_unique_id = f"group_{group_id}_current_scale"
        # Name is the group's own name at setup time - like pump
        # devices' fixed "Pump N" name above, a rename via the API
        # won't retroactively update this until a reload.
        group_name = coordinator.data.get(group_id, {}).get("name", group_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"group_{group_id}")},
            name=group_name,
            manufacturer="Reef Dose",
            model="Scaling Group",
        )

    @property
    def native_value(self) -> float | None:
        group = self.coordinator.data.get(self._group_id)
        return group.get("scalePercent") if group else None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data.coordinator

    entities: list[SensorEntity] = [
        ReefDoseLabelSensor(coordinator, pump_id) for pump_id in coordinator.data
    ]
    # Reservoir is dosed-pump-only, same restriction as the schedule
    # switches in switch.py (remainingMl is None for pumps with no
    # product assigned - see coordinator.py).
    entities.extend(
        ReefDoseReservoirSensor(coordinator, description, pump_id)
        for pump_id, pump in coordinator.data.items()
        if pump.get("remainingMl") is not None
        for description in RESERVOIR_SENSOR_DESCRIPTIONS
    )
    # Groups are dynamic (see groups_coordinator.py) - only ones that
    # exist at setup time get an entity; a group created later via the
    # API needs a reload to show up here.
    entities.extend(
        ReefDoseGroupScaleSensor(data.groups_coordinator, group_id)
        for group_id in data.groups_coordinator.data
    )

    async_add_entities(entities)
