"""Services for Reef Dose — the structured actions no single HA entity
can represent (per-slot schedule edits, group create/delete), meant to
be called from a custom Lovelace card via hass.callService rather than
from automations. Kept as services (not entities) deliberately: a
service call can take an arbitrary dict/list payload (24 slot values,
a pump-id list) the way a switch/number/button never can.

The reef-dose-service API key stays server-side here - the card never
sees it, only hass.callService('reef_dose', ...) - matching how
coordinator.py/api.py already hold it, not exposing it through
anything that ends up in Lovelace dashboard config.

Single-config-entry assumption: every handler below uses whichever
ReefDoseData is first in hass.data[DOMAIN] - reasonable for this
integration (one reef-dose-service instance), same assumption
config_flow.py's single-step flow already makes by not supporting
multiple simultaneous entries in practice. Revisit if that ever
changes.
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .api import ReefDoseApiError, ReefDoseAuthError, ReefDoseClient
from .const import DOMAIN

ATTR_PUMP_ID = "pump_id"
ATTR_GROUP_ID = "group_id"
ATTR_NAME = "name"
ATTR_PUMP_IDS = "pump_ids"
ATTR_SCALE_PERCENT = "scale_percent"
ATTR_SCHEDULE_ENABLED = "schedule_enabled"
ATTR_SPLIT_DOSE_ENABLED = "split_dose_enabled"
ATTR_SLOTS = "slots"
ATTR_DAILY_TOTAL_ML = "daily_total_ml"
ATTR_DELTA_PERCENT = "delta_percent"

SERVICE_GET_SCHEDULE = "get_schedule"
SERVICE_UPDATE_SCHEDULE = "update_schedule"
SERVICE_AUTO_DIVIDE_SCHEDULE = "auto_divide_schedule"
SERVICE_APPLY_PUMP_ADJUSTMENT = "apply_pump_adjustment"
SERVICE_GET_GROUPS = "get_groups"
SERVICE_CREATE_GROUP = "create_group"
SERVICE_UPDATE_GROUP = "update_group"
SERVICE_DELETE_GROUP = "delete_group"
SERVICE_GET_GROUP_SCHEDULE = "get_group_schedule"
SERVICE_UPDATE_GROUP_SCHEDULE = "update_group_schedule"
SERVICE_AUTO_DIVIDE_GROUP_SCHEDULE = "auto_divide_group_schedule"

_HOUR_KEYS = [f"{h:02d}" for h in range(24)]

GET_SCHEDULE_SCHEMA = vol.Schema({vol.Required(ATTR_PUMP_ID): cv.string})

UPDATE_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PUMP_ID): cv.string,
        vol.Optional(ATTR_SCHEDULE_ENABLED): cv.boolean,
        vol.Optional(ATTR_SPLIT_DOSE_ENABLED): cv.boolean,
        # Partial slots map, e.g. {"00": 1.29, "14": 0} - any hour key
        # not in HOURS is rejected by reef-dose-service itself, not
        # re-validated here (one source of truth for the hour set).
        vol.Optional(ATTR_SLOTS): {vol.In(_HOUR_KEYS): vol.Coerce(float)},
    }
)

AUTO_DIVIDE_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PUMP_ID): cv.string,
        vol.Required(ATTR_DAILY_TOTAL_ML): vol.Coerce(float),
    }
)

CREATE_GROUP_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_GROUP_ID): cv.string,
        vol.Required(ATTR_NAME): cv.string,
        vol.Required(ATTR_PUMP_IDS): [cv.string],
        vol.Optional(ATTR_SCALE_PERCENT): vol.Coerce(float),
    }
)

UPDATE_GROUP_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_GROUP_ID): cv.string,
        vol.Optional(ATTR_NAME): cv.string,
        vol.Optional(ATTR_PUMP_IDS): [cv.string],
        vol.Optional(ATTR_SCALE_PERCENT): vol.Coerce(float),
    }
)

DELETE_GROUP_SCHEMA = vol.Schema({vol.Required(ATTR_GROUP_ID): cv.string})

APPLY_PUMP_ADJUSTMENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PUMP_ID): cv.string,
        vol.Required(ATTR_DELTA_PERCENT): vol.Coerce(float),
    }
)

GET_GROUP_SCHEDULE_SCHEMA = vol.Schema({vol.Required(ATTR_GROUP_ID): cv.string})

UPDATE_GROUP_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_GROUP_ID): cv.string,
        vol.Required(ATTR_SLOTS): {vol.In(_HOUR_KEYS): vol.Coerce(float)},
    }
)

AUTO_DIVIDE_GROUP_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_GROUP_ID): cv.string,
        vol.Required(ATTR_DAILY_TOTAL_ML): vol.Coerce(float),
    }
)


def _get_client(hass: HomeAssistant) -> ReefDoseClient:
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        raise HomeAssistantError("Reef Dose is not set up")
    return next(iter(entries.values())).coordinator.client


async def _call(client_call) -> ServiceResponse:  # type: ignore[no-untyped-def]
    """Runs one ReefDoseClient call, translating its errors into
    HomeAssistantError so they surface cleanly in the UI/card instead
    of as a raw exception traceback.
    """
    try:
        return await client_call
    except ReefDoseAuthError as err:
        raise HomeAssistantError(f"reef-dose-service rejected the api key: {err}") from err
    except ReefDoseApiError as err:
        raise HomeAssistantError(f"reef-dose-service request failed: {err}") from err


async def async_setup_services(hass: HomeAssistant) -> None:
    """Registers every reef_dose.* service, once per hass instance."""
    if hass.services.has_service(DOMAIN, SERVICE_GET_SCHEDULE):
        return  # a second config entry would otherwise double-register

    def _get_data():  # type: ignore[no-untyped-def]
        return next(iter(hass.data[DOMAIN].values()))

    async def _refresh_pumps() -> None:
        await _get_data().coordinator.async_request_refresh()

    async def _refresh_groups() -> None:
        await _get_data().groups_coordinator.async_request_refresh()

    async def get_schedule(call: ServiceCall) -> ServiceResponse:
        client = _get_client(hass)
        return await _call(client.async_get_schedule(call.data[ATTR_PUMP_ID]))

    async def update_schedule(call: ServiceCall) -> ServiceResponse:
        client = _get_client(hass)
        pump_id = call.data[ATTR_PUMP_ID]
        fields = {
            key: call.data[attr]
            for attr, key in (
                (ATTR_SCHEDULE_ENABLED, "scheduleEnabled"),
                (ATTR_SPLIT_DOSE_ENABLED, "splitDoseEnabled"),
                (ATTR_SLOTS, "slots"),
            )
            if attr in call.data
        }
        result = await _call(client.async_update_schedule(pump_id, **fields))
        await _refresh_pumps()
        return result

    async def auto_divide_schedule(call: ServiceCall) -> ServiceResponse:
        client = _get_client(hass)
        result = await _call(
            client.async_auto_divide_schedule(call.data[ATTR_PUMP_ID], call.data[ATTR_DAILY_TOTAL_ML])
        )
        await _refresh_pumps()
        return result

    async def get_groups(call: ServiceCall) -> ServiceResponse:
        client = _get_client(hass)
        groups = await _call(client.async_get_groups())
        return {"groups": groups}

    async def create_group(call: ServiceCall) -> ServiceResponse:
        client = _get_client(hass)
        result = await _call(
            client.async_create_group(
                call.data[ATTR_GROUP_ID],
                call.data[ATTR_NAME],
                call.data[ATTR_PUMP_IDS],
                call.data.get(ATTR_SCALE_PERCENT),
            )
        )
        await _refresh_groups()
        return result

    async def update_group(call: ServiceCall) -> ServiceResponse:
        client = _get_client(hass)
        group_id = call.data[ATTR_GROUP_ID]
        fields = {
            key: call.data[attr]
            for attr, key in (
                (ATTR_NAME, "name"),
                (ATTR_PUMP_IDS, "pumpIds"),
                (ATTR_SCALE_PERCENT, "scalePercent"),
            )
            if attr in call.data
        }
        result = await _call(client.async_update_group(group_id, **fields))
        await _refresh_groups()
        return result

    async def delete_group(call: ServiceCall) -> None:
        client = _get_client(hass)
        await _call(client.async_delete_group(call.data[ATTR_GROUP_ID]))
        await _refresh_groups()

    async def apply_pump_adjustment(call: ServiceCall) -> ServiceResponse:
        client = _get_client(hass)
        result = await _call(
            client.async_apply_pump_adjustment(call.data[ATTR_PUMP_ID], call.data[ATTR_DELTA_PERCENT])
        )
        await _refresh_pumps()
        return result

    async def get_group_schedule(call: ServiceCall) -> ServiceResponse:
        client = _get_client(hass)
        return await _call(client.async_get_group_schedule(call.data[ATTR_GROUP_ID]))

    async def update_group_schedule(call: ServiceCall) -> ServiceResponse:
        client = _get_client(hass)
        result = await _call(
            client.async_update_group_schedule(call.data[ATTR_GROUP_ID], call.data[ATTR_SLOTS])
        )
        await _refresh_pumps()
        await _refresh_groups()
        return result

    async def auto_divide_group_schedule(call: ServiceCall) -> ServiceResponse:
        client = _get_client(hass)
        result = await _call(
            client.async_auto_divide_group_schedule(call.data[ATTR_GROUP_ID], call.data[ATTR_DAILY_TOTAL_ML])
        )
        await _refresh_pumps()
        await _refresh_groups()
        return result

    hass.services.async_register(
        DOMAIN, SERVICE_GET_SCHEDULE, get_schedule, schema=GET_SCHEDULE_SCHEMA, supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_SCHEDULE,
        update_schedule,
        schema=UPDATE_SCHEDULE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_AUTO_DIVIDE_SCHEDULE,
        auto_divide_schedule,
        schema=AUTO_DIVIDE_SCHEDULE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_GET_GROUPS, get_groups, schema=vol.Schema({}), supports_response=SupportsResponse.ONLY
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_GROUP,
        create_group,
        schema=CREATE_GROUP_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_GROUP,
        update_group,
        schema=UPDATE_GROUP_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_DELETE_GROUP, delete_group, schema=DELETE_GROUP_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_APPLY_PUMP_ADJUSTMENT,
        apply_pump_adjustment,
        schema=APPLY_PUMP_ADJUSTMENT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_GROUP_SCHEDULE,
        get_group_schedule,
        schema=GET_GROUP_SCHEDULE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_GROUP_SCHEDULE,
        update_group_schedule,
        schema=UPDATE_GROUP_SCHEDULE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_AUTO_DIVIDE_GROUP_SCHEDULE,
        auto_divide_group_schedule,
        schema=AUTO_DIVIDE_GROUP_SCHEDULE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
