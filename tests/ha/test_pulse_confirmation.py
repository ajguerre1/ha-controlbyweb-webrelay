"""Pulse confirmation, proved armed AND deliberately disarmed.

THE DISARMED HALF IS NOT OPTIONAL, AND IT IS THE POINT.

A guard tested only in its armed state cannot be distinguished from a favourable
race: if the relay in the fixture happened to be closed for an unrelated reason,
the armed test would pass while the guard did nothing. So the failure asserted
here is also run with confirmation switched off, where the SAME failure must go
unnoticed. If the disarmed run also raises, the raise is coming from somewhere
else and the armed test proves nothing.

Entities are looked up through the entity registry by unique ID rather than by a
guessed `entity_id`. A guessed id that stops matching makes every test in the
module fail for a reason unrelated to what they assert.
"""

from __future__ import annotations

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit

from custom_components.controlbyweb.const import (
    CONF_CONFIRM_PULSES,
    CONF_PULSE_SECONDS,
    CONF_RELAYS,
)

RELAY = 4  # the relay this project treats as safe: unwired on the real board


def pulse_button(hass: HomeAssistant, entry, relay: int = RELAY) -> str:
    """The entity id of a relay's pulse button, from the registry."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        BUTTON_DOMAIN, "controlbyweb", f"{entry.entry_id}_{relay}_pulse"
    )
    assert entity_id is not None, f"no pulse button registered for relay {relay}"
    return entity_id


async def press(hass: HomeAssistant, entry, relay: int = RELAY) -> None:
    """Press a pulse button, letting any error out."""
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: pulse_button(hass, entry, relay)},
        blocking=True,
    )


def close_relay_on_pulse(unit: MockModbusUnit, relay: int = RELAY) -> None:
    """Make the mock behave like the real device: an FC16 write closes the coil.

    The mock does NOT do this on its own, and that is deliberate -- a fixture
    that closed the coil automatically would let a broken pulse path look
    healthy. It is wired here, in the module whose whole subject is the
    difference between a relay that operated and one that did not, so the
    simulation is visible in the test rather than hidden in a fixture.
    """

    def on_write(event) -> None:
        if event.function_code == 0x10:
            unit.coils[relay - 1] = True

    unit.on_write(on_write)


# -- armed vs disarmed: the same failure, twice ---------------------------------


async def test_armed_confirmation_raises_when_the_relay_does_not_close(
    hass: HomeAssistant, quad_unit: MockModbusUnit, setup_entry
):
    """The command was accepted, the relay never moved, so the press must fail.

    This is the whole reason the feature exists. Under the path it replaces, a
    gate that did not open reported success.
    """
    entry = await setup_entry()
    # Deliberately no `close_relay_on_pulse`: the write is accepted and the coil
    # stays open, which is exactly the failure a caller needs to hear about.

    with pytest.raises(HomeAssistantError, match="did not close"):
        await press(hass, entry)


async def test_disarmed_confirmation_misses_the_same_failure(
    hass: HomeAssistant, quad_unit: MockModbusUnit, setup_entry, entry_options, writes
):
    """The control. Identical stimulus, confirmation off, and it must NOT raise.

    If this raised as well, the error in the armed test would not be coming from
    the guard and that test would be measuring something else entirely.
    """
    entry = await setup_entry({**entry_options, CONF_CONFIRM_PULSES: False})

    await press(hass, entry)  # must not raise

    # And the pulse itself still went out -- disarming the check must not
    # disarm the command.
    assert [w.function_code for w in writes] == [0x10]


async def test_armed_confirmation_passes_when_the_relay_closes(
    hass: HomeAssistant, quad_unit: MockModbusUnit, setup_entry
):
    """A false alarm on a working gate would be worse than no confirmation."""
    entry = await setup_entry()
    close_relay_on_pulse(quad_unit)

    await press(hass, entry)  # must not raise


# -- unknown outcomes are not failures ------------------------------------------


async def test_a_failed_confirmation_read_does_not_raise(
    hass: HomeAssistant, quad_unit: MockModbusUnit, setup_entry, caplog
):
    """ "Could not check" is not "did not happen".

    The write was accepted, so the pulse almost certainly fired and only the
    read back failed. Raising here would abort scripts on a working gate every
    time the network hiccuped -- a worse failure than not confirming.
    """
    entry = await setup_entry()

    def fail_reads_after_the_write(event) -> None:
        if event.function_code == 0x10:
            quad_unit.fail_read(0, ModbusTimeoutError("no answer"), register_type="coil")

    quad_unit.on_write(fail_reads_after_the_write)

    await press(hass, entry)  # must not raise

    assert "could not be read back" in caplog.text


async def test_a_pulse_too_short_to_check_is_not_checked(
    hass: HomeAssistant, quad_unit: MockModbusUnit, setup_entry, entry_options, caplog
):
    """Below one round trip, a negative result would mean nothing.

    The device accepts pulses down to 0.1 s, so this range is reachable by
    anyone who wants it. Confirming one would be a race the device usually
    wins, and the guard would start reporting failures on relays that worked.
    """
    entry = await setup_entry(
        {
            **entry_options,
            CONF_RELAYS: {str(r): {CONF_PULSE_SECONDS: 0.2} for r in range(1, 5)},
        }
    )

    # Note the coil is never closed, so an armed check WOULD have raised.
    await press(hass, entry)

    assert "Not confirming" in caplog.text


# -- what actually went on the wire ---------------------------------------------


async def test_the_press_sends_the_configured_duration_to_the_right_register(
    hass: HomeAssistant, quad_unit: MockModbusUnit, setup_entry, writes
):
    """Relay 4 at 1.5 s is FC16 to 0x0016 carrying [0, 16320].

    Asserted at wire level rather than as "pulse was called": the address, the
    function code and the byte order can each be wrong while the call itself
    looks perfectly right.
    """
    entry = await setup_entry()
    close_relay_on_pulse(quad_unit)

    await press(hass, entry)

    assert (writes[0].function_code, writes[0].address, writes[0].values) == (
        0x10,
        0x0016,
        [0, 16320],
    )
