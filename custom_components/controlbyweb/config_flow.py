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
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)
from modbus_connection import ModbusError, ModbusTcpParams

from .const import (
    CONF_CONFIRM_PULSES,
    CONF_PULSE_SECONDS,
    CONF_RELAY_NAME,
    CONF_RELAYS,
    CONF_UNIT_ID,
    DEFAULT_CONFIRM_PULSES,
    DOMAIN,
)
from .webrelay import (
    DEFAULT_PORT,
    DEFAULT_PULSE_SECONDS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    MAX_SCAN_INTERVAL,
    PULSE_MAX_SECONDS,
    PULSE_MIN_SECONDS,
    RELAY_COUNT,
    NotAWebRelayQuadError,
    WebRelayQuad,
)

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

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> ControlByWebOptionsFlow:
        """Return the options flow."""
        return ControlByWebOptionsFlow()

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
            except ModbusError, HomeAssistantError:
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


class ControlByWebOptionsFlow(OptionsFlow):
    """Per-relay names and pulse lengths, and how the board is polled."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show one form covering every relay plus the shared settings."""
        if user_input is not None:
            return self.async_create_entry(data=_options_from_form(user_input))

        return self.async_show_form(step_id="init", data_schema=self._schema(), last_step=True)

    def _schema(self) -> vol.Schema:
        """Build the form, seeded with what is currently configured."""
        options = self.config_entry.options
        relays = options.get(CONF_RELAYS, {})
        fields: dict[Any, Any] = {}

        for relay in range(1, RELAY_COUNT + 1):
            current = relays.get(str(relay), {})
            fields[
                vol.Optional(
                    f"{CONF_RELAY_NAME}_{relay}",
                    description={"suggested_value": current.get(CONF_RELAY_NAME, "")},
                )
            ] = TextSelector()
            # Bounded by what the DEVICE accepts, not by taste. Outside 0.1-86400
            # it clamps silently and reports success, so the form is the last
            # place a typo can still be caught.
            fields[
                vol.Required(
                    f"{CONF_PULSE_SECONDS}_{relay}",
                    default=current.get(CONF_PULSE_SECONDS, DEFAULT_PULSE_SECONDS),
                )
            ] = vol.All(
                NumberSelector(
                    NumberSelectorConfig(
                        mode=NumberSelectorMode.BOX,
                        min=PULSE_MIN_SECONDS,
                        max=PULSE_MAX_SECONDS,
                        step=0.1,
                        unit_of_measurement="s",
                    )
                ),
                vol.Coerce(float),
            )

        fields[
            vol.Required(
                CONF_CONFIRM_PULSES,
                default=options.get(CONF_CONFIRM_PULSES, DEFAULT_CONFIRM_PULSES),
            )
        ] = BooleanSelector()

        # The maximum is the device's, not a preference: it drops an idle Modbus
        # connection after about 50 seconds, so a slower poll does not reduce
        # load, it makes the next button press reconnect first.
        fields[
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            )
        ] = vol.All(
            NumberSelector(
                NumberSelectorConfig(
                    mode=NumberSelectorMode.BOX,
                    min=1,
                    max=MAX_SCAN_INTERVAL,
                    unit_of_measurement="s",
                )
            ),
            vol.Coerce(int),
        )

        return vol.Schema(fields)


def _options_from_form(user_input: dict[str, Any]) -> dict[str, Any]:
    """Fold the flat form back into per-relay options.

    Home Assistant's form schemas are flat, so the per-relay fields are suffixed
    and regrouped here. Relay keys are STRINGS: options are stored as JSON, which
    has no integer keys, so an int written here would come back as a str and
    every later lookup would silently miss.
    """
    relays: dict[str, dict[str, Any]] = {}
    for relay in range(1, RELAY_COUNT + 1):
        entry: dict[str, Any] = {CONF_PULSE_SECONDS: user_input[f"{CONF_PULSE_SECONDS}_{relay}"]}
        if name := (user_input.get(f"{CONF_RELAY_NAME}_{relay}") or "").strip():
            entry[CONF_RELAY_NAME] = name
        relays[str(relay)] = entry

    return {
        CONF_RELAYS: relays,
        CONF_CONFIRM_PULSES: user_input[CONF_CONFIRM_PULSES],
        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
    }
