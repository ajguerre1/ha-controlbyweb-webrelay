"""The ControlByWeb WebRelay-Quad integration.

The Modbus connection is not opened here. `async_get_unit` hands out a unit on a
connection shared with anything else addressing the same host and port, and
reference-counts it, so the socket is closed when the last config entry holding a
unit on it unloads.

THAT SHARING IS NOT AN OPTIMISATION HERE, IT IS THE DIFFERENCE BETWEEN WORKING
AND NOT. The board accepts exactly TWO concurrent Modbus/TCP connections. A third
is refused instantly -- accepted at the TCP level and dropped, with no Modbus
error and nothing in any log. Measured on an X-WR-4R3-E by disabling and
re-enabling this integration while probing from another machine: three failures,
then three successes, then three failures again.

Two consequences worth keeping in mind before adding a second connection anywhere
in this integration:

* One config entry must cost one connection. Anything that opens its own socket
  rather than taking a unit on the shared one halves the budget.
* Running alongside Home Assistant's YAML `modbus:` integration consumes the pair
  -- the two use different libraries and cannot share -- so during a migration no
  other tool can reach the board at all.
"""

from __future__ import annotations

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from modbus_connection import ModbusTcpParams

from .const import CONF_UNIT_ID
from .coordinator import ControlByWebConfigEntry, ControlByWebCoordinator
from .webrelay import WebRelayQuad

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SWITCH]

REQUEST_SPACING = 0.05
"""Minimum gap between requests to this unit, in seconds.

A floor rather than a throttle. Steady-state traffic is one read every ten
seconds and nowhere near this, but a pulse confirmation issues a read immediately
behind a write, and bursts to this device have previously drawn connection
resets. Spacing costs nothing when nothing is bursting.
"""


async def async_setup_entry(hass: HomeAssistant, entry: ControlByWebConfigEntry) -> bool:
    """Set up a WebRelay-Quad from a config entry."""
    unit = async_get_unit(
        hass,
        entry,
        ModbusTcpParams(host=entry.data[CONF_HOST], port=entry.data[CONF_PORT]),
        entry.data[CONF_UNIT_ID],
    )
    unit.set_message_spacing(REQUEST_SPACING)

    coordinator = ControlByWebCoordinator(hass, entry, WebRelayQuad(unit))
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options_change))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ControlByWebConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_on_options_change(
    hass: HomeAssistant, entry: ControlByWebConfigEntry
) -> None:
    """Reload so a changed scan interval or relay name actually takes effect.

    The coordinator reads its interval once, at construction. Without this, an
    options change would be saved, shown back to the user as applied, and have no
    effect until Home Assistant restarted.
    """
    await hass.config_entries.async_reload(entry.entry_id)
