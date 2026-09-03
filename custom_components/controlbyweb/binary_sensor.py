"""Relay state.

WHAT THIS SENSOR IS FOR, AND WHAT IT IS NOT FOR.

It is for spotting a relay that is stuck **closed** -- a sustained state. It is
**not** for confirming that a pulse happened, and it will not do that: a 1.5 s
pulse is over long before the next poll, so the sensor will usually show nothing
at all when a button is pressed. That is correct behaviour, not a fault, and
anyone who reads it as one will conclude the integration is broken when it is
working. Pulse confirmation is a separate mechanism on the button itself.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ControlByWebConfigEntry, relay_numbers
from .entity import ControlByWebEntity

DESCRIPTION = BinarySensorEntityDescription(key="state", translation_key="relay_state")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ControlByWebConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one state sensor per relay."""
    async_add_entities(
        ControlByWebRelaySensor(entry.runtime_data, relay, DESCRIPTION) for relay in relay_numbers()
    )


class ControlByWebRelaySensor(ControlByWebEntity, BinarySensorEntity):
    """Whether one relay's coil is currently closed."""

    @property
    def is_on(self) -> bool | None:
        """True while the relay is closed."""
        return self._is_closed
