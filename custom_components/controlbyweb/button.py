"""Pulse buttons -- the entity most installations will actually use.

A press sends function code 16 and lets the DEVICE time and release the relay.
Home Assistant does not hold it closed, which matters: if the relay were held
from here, a restart mid-pulse would leave it closed indefinitely.

Failures are raised, not logged. A script or automation that pulses a gate should
stop when the gate did not respond, rather than carrying on through the steps
that assumed it did.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_PULSE_SECONDS
from .coordinator import ControlByWebConfigEntry, relay_numbers
from .entity import ControlByWebEntity
from .webrelay import DEFAULT_PULSE_SECONDS

#: One press at a time. Two pulses overlapping on this device do not queue -- the
#: second EXTENDS the first (manual 2.4.4), so the relay stays closed longer than
#: either asked for. Serialising keeps that surprise out of normal use.
PARALLEL_UPDATES = 1

DESCRIPTION = ButtonEntityDescription(key="pulse", translation_key="relay_pulse")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ControlByWebConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one pulse button per relay."""
    async_add_entities(
        ControlByWebPulseButton(entry.runtime_data, relay, DESCRIPTION) for relay in relay_numbers()
    )


class ControlByWebPulseButton(ControlByWebEntity, ButtonEntity):
    """Pulse one relay for its configured time."""

    @property
    def _pulse_seconds(self) -> float:
        """How long to close the relay for.

        This is NOT read from the device and cannot be: the WebRelay-Quad
        implements no register-read function code, so its own configured Pulse
        Duration is unreachable over Modbus. The value here is whatever the user
        entered, and keeping it in step with the device's own setting is manual.
        """
        return float(self._relay_options.get(CONF_PULSE_SECONDS, DEFAULT_PULSE_SECONDS))

    async def async_press(self) -> None:
        """Pulse the relay, and confirm it operated if confirmation is enabled."""
        await self.coordinator.async_pulse(self._relay, self._pulse_seconds)
