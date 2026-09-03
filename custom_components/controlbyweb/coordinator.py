"""Polling the relay coils, and proving a pulse actually happened.

TWO THINGS HERE ARE NOT ARBITRARY, AND BOTH COST SOMETHING IF CHANGED.

**The scan interval has a ceiling, and it is not about freshness.** Manual 3.3:
an idle Modbus connection is dropped after "about 50 seconds". The poll is what
holds the socket open. Setting it slower does not reduce load so much as make the
next button press pay a reconnect before it can send anything -- which on a gate
is latency the user feels. `MAX_SCAN_INTERVAL` is 45.

**Pulse confirmation reads the coil back, and that is only safe because it was
measured.** The manual says any command arriving before the pulse timer expires
cancels it, which read literally would mean this feature destroys the pulse it is
confirming. On hardware, 139 coil reads landed inside a 3.0 s and a 10.0 s pulse
and neither was truncated. Anyone tempted to extend this into a tighter polling
loop during a pulse should re-run that measurement first rather than assume the
margin scales.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from modbus_connection import ModbusError

from .const import CONF_CONFIRM_PULSES, DEFAULT_CONFIRM_PULSES, DOMAIN
from .webrelay import DEFAULT_SCAN_INTERVAL, MAX_SCAN_INTERVAL, RELAY_COUNT, WebRelayQuad

_LOGGER = logging.getLogger(__name__)

CONFIRM_DELAY_FRACTION = 0.4
MAX_CONFIRM_DELAY = 0.3
"""How long after the write to look for an energised coil.

The relay closes in about 0.03 s, and a Modbus round trip on this device is
roughly 0.15 s, so anything from "immediately" to "a third of the way in" works.
The delay is capped so a long pulse is not confirmed slowly, and scaled so a
short one is not confirmed after it has already ended.
"""

MIN_CONFIRMABLE_SECONDS = 0.5
"""Below this, a pulse is not confirmed at all, and the reason is logged.

A single Modbus round trip is around 0.15 s. Confirming a 0.1 s pulse would be a
race the device usually wins, and a confirmation that reports failure on a
working relay is worse than no confirmation: it would abort scripts that were
succeeding. The device's own minimum is 0.1 s, so this range is reachable.
"""

type ControlByWebConfigEntry = ConfigEntry[ControlByWebCoordinator]


class ControlByWebCoordinator(DataUpdateCoordinator[tuple[bool, ...]]):
    """Poll all four relay coils in one request, and drive writes."""

    config_entry: ControlByWebConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ControlByWebConfigEntry,
        device: WebRelayQuad,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=timedelta(seconds=_scan_interval(entry)),
        )
        self.device = device
        self._pending_refresh: CALLBACK_TYPE | None = None

    @property
    def confirm_pulses(self) -> bool:
        """Whether a pulse is read back to prove it happened."""
        return self.config_entry.options.get(CONF_CONFIRM_PULSES, DEFAULT_CONFIRM_PULSES)

    @property
    def device_info(self) -> DeviceInfo:
        """The one relay board every entity on this config entry belongs to.

        Identified by the connection, because the device offers nothing else --
        no serial number, no model string, no device-identification object. The
        model is stated rather than read for the same reason.
        """
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.unique_id or self.config_entry.entry_id)},
            manufacturer="ControlByWeb",
            model="WebRelay-Quad",
        )

    async def _async_update_data(self) -> tuple[bool, ...]:
        """Read all four coils in a single request."""
        try:
            return await self.device.async_read_relays()
        except ModbusError as err:
            # Also what an enabled control password looks like, since it disables
            # Modbus outright. The config flow explains that; by this point the
            # integration is already set up, so the log is where it has to be said.
            raise UpdateFailed(f"Could not read the relay states: {err}") from err

    async def async_pulse(self, relay: int, seconds: float) -> None:
        """Pulse a relay, and -- if asked to -- prove that it operated.

        Raises `HomeAssistantError` only when the coil was READ and found open.
        A confirmation read that itself fails leaves the outcome unknown, and an
        unknown outcome is logged rather than raised: the pulse very likely fired
        and aborting the caller would be a false alarm on a working gate.
        """
        await self.device.async_pulse(relay, seconds)

        if not self.confirm_pulses:
            return

        if seconds < MIN_CONFIRMABLE_SECONDS:
            _LOGGER.debug(
                "Not confirming a %.2fs pulse on relay %d: shorter than one reliable "
                "round trip, so a negative result would not mean anything",
                seconds,
                relay,
            )
            return

        await asyncio.sleep(min(MAX_CONFIRM_DELAY, seconds * CONFIRM_DELAY_FRACTION))

        try:
            states = await self.device.async_read_relays()
        except ModbusError as err:
            _LOGGER.warning(
                "Could not confirm the pulse on relay %d; it was sent and probably "
                "fired, but the relay could not be read back: %s",
                relay,
                err,
            )
            return

        self.async_set_updated_data(states)

        if not states[relay - 1]:
            raise HomeAssistantError(
                f"Relay {relay} did not close when it was pulsed for {seconds}s. "
                "The command was accepted but the relay did not operate."
            )

        # Bring the entity back to 'off' promptly once the device releases it,
        # rather than leaving it showing closed until the next scheduled poll.
        #
        # Registered for cancellation on unload. A pending callback would
        # otherwise fire against a coordinator whose config entry has been
        # removed -- most visibly during a reload, which every options change
        # performs.
        self._cancel_pending_refresh()
        self._pending_refresh = async_call_later(
            self.hass, seconds + 0.5, self._async_refresh_after_pulse
        )
        self.config_entry.async_on_unload(self._cancel_pending_refresh)

    def _cancel_pending_refresh(self) -> None:
        """Drop any post-pulse refresh that has not fired yet."""
        if self._pending_refresh is not None:
            self._pending_refresh()
            self._pending_refresh = None

    async def _async_refresh_after_pulse(self, _now: object) -> None:
        """Re-read the coils once a pulse should have ended."""
        self._pending_refresh = None
        await self.async_request_refresh()

    async def async_set_relay(self, relay: int, on: bool) -> None:
        """Latch a relay on or off, then reflect the new state immediately."""
        await self.device.async_set_relay(relay, on)
        await self.async_request_refresh()


def _scan_interval(entry: ControlByWebConfigEntry) -> int:
    """The poll interval, clamped below the device's connection timeout.

    Clamped rather than validated: an entry written before the ceiling existed,
    or edited by hand, must not be able to set an interval that quietly breaks
    every button press.
    """
    configured = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    return max(1, min(int(configured), MAX_SCAN_INTERVAL))


def relay_numbers() -> range:
    """The relays this device has, numbered as the manual numbers them: 1-4."""
    return range(1, RELAY_COUNT + 1)
