"""Adding a WebRelay-Quad by address, and confirming it is one.

Identification is not a nicety here. This integration writes function-code 16 to
registers 0x0010-0x0016; on a device that is not a WebRelay-Quad those addresses
mean something else entirely. So the flow proves what it is talking to before it
creates anything, and reports "reached something else" differently from "could
not reach it" -- the two have different fixes.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)
from modbus_connection import ModbusError, ModbusTcpParams

from .const import CONF_UNIT_ID, DOMAIN
from .webrelay import DEFAULT_PORT, DEFAULT_UNIT_ID, NotAWebRelayQuadError, WebRelayQuad

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=65535)),
            vol.Coerce(int),
        ),
        # 0-255, not the Modbus specification's 1-247. The WebRelay-Quad's manual
        # specifies 255, and the library accepts it.
        vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.All(
            NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=0, max=255)),
            vol.Coerce(int),
        ),
    }
)


class ControlByWebConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a ControlByWeb WebRelay-Quad."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for an address and check a WebRelay-Quad answers there."""
        errors: dict[str, str] = {}

        if user_input is not None:
            params = ModbusTcpParams(host=user_input[CONF_HOST], port=user_input[CONF_PORT])
            try:
                async with async_get_temporary_unit(
                    self.hass, params, user_input[CONF_UNIT_ID]
                ) as unit:
                    await WebRelayQuad(unit).async_identify()
            except NotAWebRelayQuadError as err:
                # Reached a device, and it is the wrong one. Distinct from
                # cannot_connect because the fix is a different address, not a
                # different setting.
                _LOGGER.debug("Device at %s is not a WebRelay-Quad: %s", params.host, err)
                errors["base"] = "not_a_webrelay_quad"
            except (ModbusError, HomeAssistantError):
                # Also the symptom of the device's control password being on,
                # which disables Modbus outright. The message says so, because
                # nothing else in Home Assistant will ever mention it.
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # The device offers no serial number, no vendor string and no
                # device-identification object -- every read but FC1 is an
                # illegal function. So identity is the address it answers on,
                # and re-addressing the device reads as a new one. There is no
                # alternative available.
                await self.async_set_unique_id(
                    f"{params.host}:{user_input[CONF_PORT]}:{user_input[CONF_UNIT_ID]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="WebRelay-Quad", data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
