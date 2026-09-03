"""Talking to a ControlByWeb WebRelay-Quad over Modbus/TCP.

No Home Assistant imports live in this package. It takes a `ModbusUnit` -- the
backend-neutral handle Home Assistant's `modbus` integration hands out from
`async_get_unit` -- and knows nothing else about where it came from.

WHAT THIS DEVICE CAN AND CANNOT DO, MEASURED
--------------------------------------------
Manual rev 2.5 section 3.3 lists four function codes, and a read-only survey of a
live X-WR-4R3-E agreed with it exactly:

    FC1  read coils          coils 0-3 only; a fifth is an illegal data address
    FC5  write single coil   latch a relay on or off
    FC15 write multiple coils
    FC16 write multiple registers -- the pulse

Everything else -- FC2, FC3, FC4, FC7, FC17, FC43/14 -- answers *illegal
function*. FC3 does so at every address, not merely outside a range. Three
consequences run through this whole module:

* **The pulse registers cannot be read back.** A write is confirmed by watching
  the coil, or it is not confirmed at all.
* **There is no device identity** -- no serial number, no vendor string. What
  `async_identify` checks is behaviour, because there is nothing to interrogate.
* **The device's own configured pulse duration is unreadable.** It lives on the
  HTTP control page, and this device speaks HTTP/0.9, which no Home Assistant
  HTTP client will parse. Durations must be supplied by the caller.

Reads are safe during a pulse. The manual says any command arriving before the
pulse timer expires cancels it, which read literally would mean that observing a
pulse destroys it. Measured on an unwired relay: 139 coil reads landed inside a
3.0 s and a 10.0 s pulse and neither was truncated (released at 3.31 s and
10.24 s). That measurement is what makes `WebRelayQuad.async_pulse` confirmable.
"""

from __future__ import annotations

import struct

from modbus_connection import (
    IllegalDataAddressError,
    IllegalFunctionError,
    ModbusUnit,
)

from .const import (
    COIL_BASE,
    PULSE_MAX_SECONDS,
    PULSE_MIN_SECONDS,
    PULSE_REGISTERS,
    RELAY_COUNT,
)
from .errors import NotAWebRelayQuadError, PulseDurationError

__all__ = ["WebRelayQuad", "encode_pulse"]


def encode_pulse(seconds: float) -> list[int]:
    """The pulse duration as two registers, in the order the device wants them.

    Section 3.3.4: the duration is an IEEE-754 float whose "four data bytes are
    treated as two individual big endian 16-bit words but the least significant
    word is sent first. In other words, the 32-byte floating point number
    represented as ABCD is sent as CDAB."

    The manual's own worked example is 10 seconds as `00 00 41 20`, which this
    reproduces, and `tests/test_encode.py` pins it alongside the two durations
    in production use.

    Written out rather than delegated to
    `modbus_connection.encode.encode_float32`, for two reasons: that helper lives
    in a submodule the package does not re-export, and it cannot enforce the
    range below. The test suite asserts the two agree, so a divergence is caught
    rather than inherited.

    Raises `PulseDurationError` outside 0.1-86400 s. The device clamps silently
    in that case, which would turn a misplaced decimal point into a working
    command with the wrong behaviour.
    """
    if not PULSE_MIN_SECONDS <= seconds <= PULSE_MAX_SECONDS:
        raise PulseDurationError(
            f"pulse duration {seconds}s is outside the device's "
            f"{PULSE_MIN_SECONDS}-{PULSE_MAX_SECONDS}s range"
        )
    high, low = struct.unpack(">HH", struct.pack(">f", seconds))
    return [low, high]


def _check_relay(relay: int) -> None:
    """Reject a relay number this device does not have, before it reaches the wire."""
    if not 1 <= relay <= RELAY_COUNT:
        raise ValueError(f"relay {relay} does not exist; this device has {RELAY_COUNT}")


class WebRelayQuad:
    """One WebRelay-Quad, addressed through a Modbus unit."""

    def __init__(self, unit: ModbusUnit) -> None:
        """Hold the unit this device is reached through."""
        self._unit = unit

    async def async_read_relays(self) -> tuple[bool, ...]:
        """The state of all four relay coils, from a single FC1 read.

        One read rather than four. Section 3.3.1 constrains the shape anyway --
        "relays 1 and 4 cannot be read without reading relays 2 & 3" -- so a
        full-width read is both the cheapest option and the only tidy one.
        """
        coils = await self._unit.read_coils(COIL_BASE, RELAY_COUNT)
        return tuple(bool(state) for state in coils[:RELAY_COUNT])

    async def async_pulse(self, relay: int, seconds: float) -> None:
        """Pulse one relay for `seconds`, then let the device release it.

        This is the Modbus equivalent of the device's own `relayNState=2`. The
        device turns the relay on immediately and off when its timer expires;
        nothing here holds it.

        Note that repeated pulses EXTEND rather than restart or queue -- section
        2.4.4: "the relay will go off at the time of the last command plus the
        Pulse Duration time". Callers that can fire in bursts should expect a
        longer single pulse, not several.
        """
        _check_relay(relay)
        await self._unit.write_registers(PULSE_REGISTERS[relay - 1], encode_pulse(seconds))

    async def async_set_relay(self, relay: int, on: bool) -> None:
        """Latch one relay on or off (FC5), with no timer.

        A latched relay stays latched. On hardware wired to a door or gate
        release that is a fault state, not a feature, which is why the entity in
        front of this is disabled by default.
        """
        _check_relay(relay)
        await self._unit.write_coil(COIL_BASE + relay - 1, on)

    async def async_identify(self) -> None:
        """Confirm the device at this address really is a WebRelay-Quad.

        There is no identity register to read (see the module docstring), so this
        tests behaviour instead. All three must hold:

            read_coils(0, 4)             succeeds       -- four coils exist
            read_coils(4, 1)             illegal ADDRESS -- and only four
            read_holding_registers(0, 1) illegal FUNCTION -- no register space

        The third is the discriminating one: essentially every other Modbus
        device has a holding-register space, so a device that answers FC3 at all
        is not this one. The check runs before any entity is created because this
        integration writes -- an unrecognised device would otherwise receive FC16
        writes into a register map that means something else entirely.

        Raises `NotAWebRelayQuadError`. Transport failures propagate unchanged;
        "could not reach it" and "reached something else" are different answers
        and the config flow reports them differently.

        The exception types below are `modbus_connection`'s own, not tmodbus's:
        the backend translates a Modbus exception response through
        `ModbusExceptionError.from_code`, so the typed subclass is what reaches a
        caller regardless of which backend is in use.
        """
        await self._unit.read_coils(COIL_BASE, RELAY_COUNT)

        try:
            await self._unit.read_coils(COIL_BASE + RELAY_COUNT, 1)
        except IllegalDataAddressError:
            pass
        else:
            raise NotAWebRelayQuadError(
                f"device answered a read of coil {RELAY_COUNT}, so it has more than "
                f"{RELAY_COUNT} relays and is not a WebRelay-Quad"
            )

        try:
            await self._unit.read_holding_registers(0, 1)
        except IllegalFunctionError:
            pass
        else:
            raise NotAWebRelayQuadError(
                "device answered a holding-register read; a WebRelay-Quad implements "
                "no register-read function code at all"
            )
