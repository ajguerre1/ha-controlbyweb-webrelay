"""Latching switches -- present, wired, and off by default.

WHY THESE ARE DISABLED UNTIL ASKED FOR.

A WebRelay-Quad is usually wired to something momentary: a door release, a gate
trigger, a doorbell. On those, a relay that stays closed is a fault. An
enabled-by-default switch would put a one-tap latch for a gate on every dashboard
that happens to show the device, and the tap that does it looks exactly like the
tap that opens it.

Dropping function code 5 entirely was the alternative and was rejected: it is the
only way to release a relay that has stuck closed, and some relays legitimately
drive a lamp or a pump. So the capability ships and the exposure does not --
`entity_registry_enabled_default = False`, the same pattern `solaredge_modbus`
uses for the export-control flags an installer has to opt into.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ControlByWebConfigEntry, relay_numbers
from .entity import ControlByWebEntity

#: Serialised for the same reason as the pulse buttons: a coil write arriving
#: during a pulse cancels the pulse (manual 3.3), so overlapping writes to this
#: device produce outcomes that depend on ordering.
PARALLEL_UPDATES = 1

DESCRIPTION = SwitchEntityDescription(
    key="latch",
    translation_key="relay_latch",
    entity_registry_enabled_default=False,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ControlByWebConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one latching switch per relay."""
    async_add_entities(
        ControlByWebLatchSwitch(entry.runtime_data, relay, DESCRIPTION) for relay in relay_numbers()
    )


class ControlByWebLatchSwitch(ControlByWebEntity, SwitchEntity):
    """Hold one relay closed until it is turned off."""

    @property
    def is_on(self) -> bool | None:
        """True while the relay is closed.

        The same coil the state sensor reads. They agree because they come from
        one poll, not two.
        """
        return self._is_closed

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Close the relay and leave it closed."""
        await self.coordinator.async_set_relay(self._relay, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Open the relay. Also the way to release one that has stuck closed."""
        await self.coordinator.async_set_relay(self._relay, False)
