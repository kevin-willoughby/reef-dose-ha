"""Number platform for Reef Dose — manual dose amount and calibration measured ml.

These are plain values held on the coordinator (not polled from the
device), read by the matching button in button.py at press time -
see button.py's ReefDoseManualDoseButton / ReefDoseApplyCalibrationButton.
"""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_DOSE_ML, DOMAIN
from .coordinator import ReefDoseCoordinator


class _ReefDoseMlNumber(NumberEntity):
    """Base for a plain ml value backed by one coordinator dict, keyed by pump id."""

    _attr_has_entity_name = True
    _attr_native_min_value = 0.01
    _attr_native_max_value = 50
    _attr_native_step = 0.01
    _attr_native_unit_of_measurement = "mL"
    _attr_mode = NumberMode.BOX

    def __init__(self, pump_id: str, store: dict[str, float]) -> None:
        self._pump_id = pump_id
        self._store = store
        self._store.setdefault(pump_id, DEFAULT_DOSE_ML)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pump_id)},
            name=f"Pump {pump_id}",
            manufacturer="Reef Dose",
            model="Pump",
        )

    @property
    def native_value(self) -> float:
        return self._store[self._pump_id]

    async def async_set_native_value(self, value: float) -> None:
        self._store[self._pump_id] = value
        self.async_write_ha_state()


class ReefDoseManualDoseMlNumber(_ReefDoseMlNumber):
    """The amount the Manual Dose button will fire for this pump."""

    _attr_name = "Manual Dose Amount"

    def __init__(self, coordinator: ReefDoseCoordinator, pump_id: str) -> None:
        super().__init__(pump_id, coordinator.manual_dose_ml)
        self._attr_unique_id = f"{pump_id}_manual_dose_ml"


class ReefDoseCalibrationMeasuredMlNumber(_ReefDoseMlNumber):
    """The measured ml the Apply Calibration button will submit."""

    _attr_name = "Calibration Measured Amount"

    def __init__(self, coordinator: ReefDoseCoordinator, pump_id: str) -> None:
        super().__init__(pump_id, coordinator.calibration_measured_ml)
        self._attr_unique_id = f"{pump_id}_calibration_measured_ml"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ReefDoseCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[NumberEntity] = [
        ReefDoseManualDoseMlNumber(coordinator, pump_id) for pump_id in coordinator.data
    ]
    # Calibration is dosed-pump-only, same restriction as the schedule
    # switches in switch.py (scheduleEnabled is None for pumps with no
    # product assigned).
    entities.extend(
        ReefDoseCalibrationMeasuredMlNumber(coordinator, pump_id)
        for pump_id, pump in coordinator.data.items()
        if pump.get("scheduleEnabled") is not None
    )

    async_add_entities(entities)
