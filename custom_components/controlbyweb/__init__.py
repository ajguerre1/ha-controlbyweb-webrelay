"""The ControlByWeb WebRelay-Quad integration.

The Modbus connection is not opened here. `async_get_unit` hands out a unit on a
connection shared with anything else addressing the same host and port, and
reference-counts it, so the socket is closed when the last config entry holding a
unit on it unloads. That matters on this hardware: it is a small embedded web
server, and it accepts a limited number of connections.
"""

from __future__ import annotations

from homeassistant.components.modbus import async_get_unit
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from modbus_connection import ModbusTcpParams

from .const import CONF_UNIT_ID
from .webrelay import WebRelayQuad

PLATFORMS: list[Platform] = []

type ControlByWebConfigEntry = ConfigEntry[WebRelayQuad]


async def async_setup_entry(hass: HomeAssistant, entry: ControlByWebConfigEntry) -> bool:
    """Set up a WebRelay-Quad from a config entry."""
    unit = async_get_unit(
        hass,
        entry,
        ModbusTcpParams(host=entry.data[CONF_HOST], port=entry.data[CONF_PORT]),
        entry.data[CONF_UNIT_ID],
    )

    entry.runtime_data = WebRelayQuad(unit)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ControlByWebConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
