"""Number platform for Reef Dose — manual dose amount, calibration measured
ml, auto-divide daily total, and a per-group manual overall adjustment.

Every one of these is a plain pending value held on a coordinator (not
polled from the device), read by a matching button in button.py at
press time - see ReefDoseManualDoseButton / ReefDoseApplyCalibrationButton
/ ReefDoseAutoDivideButton / ReefDoseApplyGroupAdjustmentButton. None of
these write straight through on change; the resulting absolute group
scale is exposed read-only instead, as a sensor (sensor.py's
ReefDoseGroupScaleSensor).
"""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_DOSE_ML, DOMAIN
from .coordinator import ReefDoseCoordinator
from .groups_coordinator import ReefDoseGroupsCoordinator


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


class ReefDoseDailyTotalMlNumber(NumberEntity):
    """The total ml/day the Auto-Divide Schedule button will evenly split
    across all 24 hourly slots (requirements.md Section 3).

    Bounds match AutoDivideScheduleDto in reef-dose-service (0-1200ml,
    24 slots at each one's own 50ml cap) - wider than the per-slot
    Manual Dose Amount number above, and defaults to 0 rather than
    DEFAULT_DOSE_ML so pressing Auto-Divide before ever touching this
    can't silently zero out a real schedule.
    """

    _attr_has_entity_name = True
    _attr_name = "Daily Total (Auto-Divide)"
    _attr_native_min_value = 0
    _attr_native_max_value = 1200
    _attr_native_step = 0.01
    _attr_native_unit_of_measurement = "mL"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: ReefDoseCoordinator, pump_id: str) -> None:
        self._pump_id = pump_id
        self._store = coordinator.daily_total_ml
        self._store.setdefault(pump_id, 0.0)
        self._attr_unique_id = f"{pump_id}_daily_total_ml"
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


class ReefDoseGroupAdjustmentNumber(NumberEntity):
    """Pending "Manual Overall Adjustment" delta (%) for one scaling
    group - requirements.md Section 5, named to match the existing
    Dosetronic app's own term for this exact action (requirements.md
    Section 3).

    This holds the DELTA to apply, not the group's current absolute
    scale - entering -10 and pressing Apply (button.py's
    ReefDoseApplyGroupAdjustmentButton) decreases every member pump's
    full 24-hour schedule by 10% of whatever it's CURRENTLY at (not
    10 percentage points off the fixed 100% base), preserving the
    ratio between pumps in the group. Compounds like any "adjust by
    X%" control: -10 applied twice takes a group from 100% -> 90% ->
    81%, not straight to 80%. Resets to 0 after each Apply - see
    ReefDoseGroupScaleSensor in sensor.py for the resulting absolute
    value.
    """

    _attr_has_entity_name = True
    _attr_name = "Manual Overall Adjustment"
    _attr_native_min_value = -100
    _attr_native_max_value = 1000
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: ReefDoseGroupsCoordinator, group_id: str) -> None:
        self._group_id = group_id
        self._store = coordinator.pending_adjustment
        self._store.setdefault(group_id, 0.0)
        self._attr_unique_id = f"group_{group_id}_adjustment"
        # Name is the group's own name at setup time - like pump
        # devices' fixed "Pump N" name (see switch.py), a rename via
        # the API won't retroactively update this until a reload.
        group_name = coordinator.data.get(group_id, {}).get("name", group_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"group_{group_id}")},
            name=group_name,
            manufacturer="Reef Dose",
            model="Scaling Group",
        )

    @property
    def native_value(self) -> float:
        return self._store[self._group_id]

    async def async_set_native_value(self, value: float) -> None:
        self._store[self._group_id] = value
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data.coordinator

    entities: list[NumberEntity] = [
        ReefDoseManualDoseMlNumber(coordinator, pump_id) for pump_id in coordinator.data
    ]
    # Calibration and daily-total are dosed-pump-only, same restriction
    # as the schedule switches in switch.py (scheduleEnabled is None
    # for pumps with no product assigned).
    entities.extend(
        number_cls(coordinator, pump_id)
        for pump_id, pump in coordinator.data.items()
        if pump.get("scheduleEnabled") is not None
        for number_cls in (ReefDoseCalibrationMeasuredMlNumber, ReefDoseDailyTotalMlNumber)
    )
    # Groups are dynamic (see groups_coordinator.py) - only ones that
    # exist at setup time get an entity; a group created later via the
    # API needs a reload to show up here.
    entities.extend(
        ReefDoseGroupAdjustmentNumber(data.groups_coordinator, group_id)
        for group_id in data.groups_coordinator.data
    )

    async_add_entities(entities)
