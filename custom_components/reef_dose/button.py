"""Button platform for Reef Dose — fire a pump's prime pulse.

Every pump gets one, dosed or not (priming doesn't need a product
assigned), unlike the schedule-backed switches in switch.py.
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_DOSE_ML, DOMAIN
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


class ReefDoseManualDoseButton(ButtonEntity):
    """Fires a one-off dose of whatever the Manual Dose Amount number holds."""

    _attr_has_entity_name = True
    _attr_name = "Manual Dose"

    def __init__(self, coordinator: ReefDoseCoordinator, pump_id: str) -> None:
        self._coordinator = coordinator
        self._pump_id = pump_id
        self._attr_unique_id = f"{pump_id}_manual_dose"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pump_id)},
            name=f"Pump {pump_id}",
            manufacturer="Reef Dose",
            model="Pump",
        )

    async def async_press(self) -> None:
        ml = self._coordinator.manual_dose_ml.get(self._pump_id, DEFAULT_DOSE_ML)
        await self._coordinator.client.async_manual_dose(self._pump_id, ml)


class ReefDoseStartCalibrationButton(ButtonEntity):
    """Starts a calibration run; stashes the returned sessionId for Apply."""

    _attr_has_entity_name = True
    _attr_name = "Start Calibration"

    def __init__(self, coordinator: ReefDoseCoordinator, pump_id: str) -> None:
        self._coordinator = coordinator
        self._pump_id = pump_id
        self._attr_unique_id = f"{pump_id}_start_calibration"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pump_id)},
            name=f"Pump {pump_id}",
            manufacturer="Reef Dose",
            model="Pump",
        )

    async def async_press(self) -> None:
        session_id = await self._coordinator.client.async_start_calibration(self._pump_id)
        self._coordinator.calibration_sessions[self._pump_id] = session_id
        # Prompts the Calibrating binary sensor to flip on promptly,
        # rather than waiting for the next minute-interval poll - see
        # binary_sensor.py and the guided-flow Lovelace example in
        # README.
        await self._coordinator.async_request_refresh()


class ReefDoseRefillReservoirButton(ButtonEntity):
    """Resets the reservoir-remaining sensor to the full-volume number's value."""

    _attr_has_entity_name = True
    _attr_name = "Refill Reservoir"

    def __init__(self, coordinator: ReefDoseCoordinator, pump_id: str) -> None:
        self._coordinator = coordinator
        self._pump_id = pump_id
        self._attr_unique_id = f"{pump_id}_refill_reservoir"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pump_id)},
            name=f"Pump {pump_id}",
            manufacturer="Reef Dose",
            model="Pump",
        )

    async def async_press(self) -> None:
        await self._coordinator.client.async_refill_reservoir(self._pump_id)
        await self._coordinator.async_request_refresh()


class ReefDoseAutoDivideButton(ButtonEntity):
    """Evenly splits the Daily Total (Auto-Divide) number across all 24
    hourly slots (requirements.md Section 3) and writes it straight to
    the device - the schedule's starting point, not its end state;
    individual slots can still be hand-edited afterward (not yet
    exposed here - see architecture.md's open items).
    """

    _attr_has_entity_name = True
    _attr_name = "Apply Auto-Divide Schedule"

    def __init__(self, coordinator: ReefDoseCoordinator, pump_id: str) -> None:
        self._coordinator = coordinator
        self._pump_id = pump_id
        self._attr_unique_id = f"{pump_id}_auto_divide_schedule"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pump_id)},
            name=f"Pump {pump_id}",
            manufacturer="Reef Dose",
            model="Pump",
        )

    async def async_press(self) -> None:
        daily_total_ml = self._coordinator.daily_total_ml.get(self._pump_id, 0.0)
        await self._coordinator.client.async_auto_divide_schedule(self._pump_id, daily_total_ml)
        await self._coordinator.async_request_refresh()


class ReefDoseApplyCalibrationButton(ButtonEntity):
    """Applies the last Start Calibration session using the measured-ml number.

    The firmware itself rejects a stale/missing session id (see
    reef-dose-service's applyCalibration) - this just raises early with a
    clearer message when Start Calibration was never pressed this session.
    """

    _attr_has_entity_name = True
    _attr_name = "Apply Calibration"

    def __init__(self, coordinator: ReefDoseCoordinator, pump_id: str) -> None:
        self._coordinator = coordinator
        self._pump_id = pump_id
        self._attr_unique_id = f"{pump_id}_apply_calibration"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, pump_id)},
            name=f"Pump {pump_id}",
            manufacturer="Reef Dose",
            model="Pump",
        )

    async def async_press(self) -> None:
        session_id = self._coordinator.calibration_sessions.get(self._pump_id)
        if session_id is None:
            raise HomeAssistantError(
                f"No calibration session for pump {self._pump_id} - press Start Calibration first"
            )
        measured_ml = self._coordinator.calibration_measured_ml.get(self._pump_id, DEFAULT_DOSE_ML)
        await self._coordinator.client.async_apply_calibration(
            self._pump_id, session_id, measured_ml
        )
        # Clears the in-progress flag the Calibrating binary sensor
        # reads (see binary_sensor.py) - completes the guided
        # Start -> enter value -> Apply flow a Lovelace conditional
        # card drives off that sensor (see README).
        self._coordinator.calibration_sessions.pop(self._pump_id, None)
        await self._coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id].coordinator

    entities: list[ButtonEntity] = [
        ReefDosePrimeButton(coordinator, pump_id) for pump_id in coordinator.data
    ]
    entities.extend(
        ReefDoseManualDoseButton(coordinator, pump_id) for pump_id in coordinator.data
    )
    # Calibration and refill are dosed-pump-only, same restriction as
    # the schedule switches in switch.py.
    entities.extend(
        button_cls(coordinator, pump_id)
        for pump_id, pump in coordinator.data.items()
        if pump.get("scheduleEnabled") is not None
        for button_cls in (
            ReefDoseStartCalibrationButton,
            ReefDoseApplyCalibrationButton,
            ReefDoseRefillReservoirButton,
            ReefDoseAutoDivideButton,
        )
    )

    async_add_entities(entities)
