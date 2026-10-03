"""Config flow: enter reef-dose-service's host + api key, validate, done.

Unlike Alkatronic (one account, auto-discover devices), there's nothing
to discover here beyond what async_get_pump_ids() already returns on
every poll - so this flow is a single step, no device-selection step
needed.
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ReefDoseApiError, ReefDoseAuthError, ReefDoseClient
from .const import CONF_API_KEY, CONF_HOST, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_API_KEY): str,
    }
)


class ReefDoseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the setup UI: host + api key, validated with a real request."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = ReefDoseClient(session, user_input[CONF_HOST], user_input[CONF_API_KEY])
            try:
                pump_ids = await client.async_get_pump_ids()
            except ReefDoseAuthError:
                errors["base"] = "invalid_auth"
            except (ReefDoseApiError, aiohttp.ClientError):
                errors["base"] = "cannot_connect"
            else:
                if not pump_ids:
                    errors["base"] = "no_pumps"
                else:
                    await self.async_set_unique_id(user_input[CONF_HOST])
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"Reef Dose ({user_input[CONF_HOST]})", data=user_input
                    )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
