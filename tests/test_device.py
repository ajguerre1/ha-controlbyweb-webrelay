"""What `WebRelayQuad` puts on the wire, and what it refuses to put there.

Assertions are made against `WriteEvent` -- function code, address, raw values --
rather than against the method that was called. Testing "pulse() called
write_registers" would pass with the wrong address, the wrong function code and
the wrong byte order, which are the three ways this can be wrong on hardware.
"""

from __future__ import annotations

import pytest
from modbus_connection import IllegalDataAddressError, IllegalFunctionError, ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit
from webrelay import NotAWebRelayQuadError, PulseDurationError, WebRelayQuad

# -- reading --------------------------------------------------------------------


async def test_reads_all_four_relays_in_one_request(quad_unit: MockModbusUnit):
    """Four states, one FC1 read at address 0.

    Not four reads. Section 3.3.1 forbids reaching relay 4 without also reading
    2 and 3, and one full-width read is 2.7x less traffic than the four separate
    polls this replaces.
    """
    quad_unit.coils = {0: False, 1: True, 2: False, 3: True}

    assert await WebRelayQuad(quad_unit).async_read_relays() == (False, True, False, True)

    assert len(quad_unit.read_events) == 1
    event = quad_unit.read_events[0]
    assert (event.register_type, event.address, event.count) == ("coil", 0, 4)


async def test_read_failure_propagates(quad_unit: MockModbusUnit):
    """A device that is not answering must surface as an error, not as all-off.

    Returning a default would present four de-energised relays, which is exactly
    what a healthy device looks like -- the failure would be invisible.
    """
    quad_unit.fail_requests(ModbusTimeoutError("no answer"))

    with pytest.raises(ModbusTimeoutError):
        await WebRelayQuad(quad_unit).async_read_relays()


# -- pulsing --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("relay", "address"),
    [(1, 0x0010), (2, 0x0012), (3, 0x0014), (4, 0x0016)],
)
async def test_pulse_targets_the_documented_register(quad_unit, writes, relay, address):
    """Each relay has its own pulse register, two apart, per section 3.3.4."""
    await WebRelayQuad(quad_unit).async_pulse(relay, 1.5)

    assert len(writes) == 1
    assert (writes[0].function_code, writes[0].address) == (0x10, address)


async def test_pulse_sends_the_manuals_own_example_bytes(quad_unit, writes):
    """Relay 1 for 10 s is FC16 to 0x0010 carrying `00 00 41 20`."""
    await WebRelayQuad(quad_unit).async_pulse(1, 10.0)

    assert writes == [
        type(writes[0])(
            register_type="holding",
            address=0x0010,
            values=[0x0000, 0x4120],
            function_code=0x10,
        )
    ]


@pytest.mark.parametrize(
    ("relay", "seconds", "address", "values"),
    [(1, 3.0, 0x0010, [0, 16448]), (2, 1.5, 0x0012, [0, 16320])],
)
async def test_pulse_reproduces_the_live_yaml_calls(
    quad_unit, writes, relay, seconds, address, values
):
    """Byte-identical to the `modbus.write_register` calls in production today.

    This is the assertion that makes cutover a like-for-like swap rather than a
    change of behaviour dressed as a refactor.
    """
    await WebRelayQuad(quad_unit).async_pulse(relay, seconds)

    assert (writes[0].address, writes[0].values) == (address, values)


async def test_pulse_does_not_touch_the_coil(quad_unit, writes):
    """The DEVICE energises and releases the relay. This code only asks.

    Pinned because the opposite -- writing the coil on, then off after a sleep --
    is the obvious wrong implementation: it would work, it would look correct in
    every log, and it would leave a relay latched on for good if Home Assistant
    restarted mid-pulse.
    """
    await WebRelayQuad(quad_unit).async_pulse(4, 3.0)

    assert [w.function_code for w in writes] == [0x10]
    assert quad_unit.coils[3] is False


@pytest.mark.parametrize("seconds", [0.0, 0.09, 86400.1])
async def test_pulse_rejects_out_of_range_before_the_wire(quad_unit, writes, seconds):
    """Nothing is sent at all. The device would have clamped and reported success."""
    with pytest.raises(PulseDurationError):
        await WebRelayQuad(quad_unit).async_pulse(1, seconds)

    assert writes == []


@pytest.mark.parametrize("relay", [0, 5, -1])
async def test_pulse_rejects_a_relay_that_does_not_exist(quad_unit, writes, relay):
    """Relay 0 or 5 must not become an off-by-one write to a real register.

    `PULSE_REGISTERS[relay - 1]` would index a valid tuple entry for relay 0 --
    Python's negative indexing makes it the LAST register, so relay 0 would pulse
    relay 4. That silent wraparound is the reason this check exists.
    """
    with pytest.raises(ValueError):
        await WebRelayQuad(quad_unit).async_pulse(relay, 1.5)

    assert writes == []


# -- latching -------------------------------------------------------------------


@pytest.mark.parametrize(("relay", "coil"), [(1, 0), (2, 1), (3, 2), (4, 3)])
async def test_set_relay_writes_the_matching_coil(quad_unit, writes, relay, coil):
    """Relay N is coil N-1 (section 3.3.1), by FC5."""
    await WebRelayQuad(quad_unit).async_set_relay(relay, True)

    assert (writes[0].function_code, writes[0].address, writes[0].values) == (0x05, coil, [True])


async def test_set_relay_can_release(quad_unit, writes):
    """Turning a latched relay off is the recovery path for a stuck one."""
    quad_unit.coils[3] = True

    await WebRelayQuad(quad_unit).async_set_relay(4, False)

    assert writes[0].values == [False]


@pytest.mark.parametrize("relay", [0, 5])
async def test_set_relay_rejects_a_relay_that_does_not_exist(quad_unit, writes, relay):
    """Same wraparound hazard as the pulse path, and the same refusal."""
    with pytest.raises(ValueError):
        await WebRelayQuad(quad_unit).async_set_relay(relay, True)

    assert writes == []


# -- identification -------------------------------------------------------------


async def test_identify_accepts_a_webrelay_quad(quad_unit: MockModbusUnit):
    """The fixture answers as the surveyed hardware does, so this must pass."""
    await WebRelayQuad(quad_unit).async_identify()


async def test_identify_rejects_a_device_with_more_than_four_coils(quad_unit: MockModbusUnit):
    """A bigger relay board or a gateway answers a fifth coil. This one does not."""
    quad_unit.fail_read(4, None, register_type="coil")
    quad_unit.coils[4] = False

    with pytest.raises(NotAWebRelayQuadError, match="more than 4"):
        await WebRelayQuad(quad_unit).async_identify()


async def test_identify_rejects_a_device_with_holding_registers(quad_unit: MockModbusUnit):
    """The discriminating probe.

    An inverter, a meter or a PLC all answer FC3. Pointing this integration at
    one of them would fire FC16 writes into a register map that means something
    else, which is why identification happens before any entity exists.
    """
    for address in range(0x30):
        quad_unit.fail_read(address, None, register_type="holding")
    quad_unit.holding = {0: 0}

    with pytest.raises(NotAWebRelayQuadError, match="register-read"):
        await WebRelayQuad(quad_unit).async_identify()


async def test_identify_lets_transport_failures_through(quad_unit: MockModbusUnit):
    """ "Could not reach it" is not "reached something else".

    The config flow reports them differently -- one says check the address and
    the control password, the other says this is the wrong device -- so this
    layer must not collapse them into one error.
    """
    quad_unit.fail_requests(ModbusTimeoutError("no answer"))

    with pytest.raises(ModbusTimeoutError):
        await WebRelayQuad(quad_unit).async_identify()


async def test_identify_does_not_write(quad_unit: MockModbusUnit, writes):
    """Identification runs against an unknown device, so it must be read-only.

    If the device turns out to be something else, the only thing that touched it
    was three reads.
    """
    await WebRelayQuad(quad_unit).async_identify()

    assert writes == []


async def test_identify_probes_are_not_silently_skipped(quad_unit: MockModbusUnit):
    """All three probes must actually run.

    A guard the code documents but never executes manufactures confidence, and
    both negative cases above would still pass if the probe they exercise were
    the ONLY one running. Counting the reads pins that all three happen.
    """
    await WebRelayQuad(quad_unit).async_identify()

    attempted = [(e.register_type, e.address, e.count) for e in quad_unit.read_events]
    assert attempted == [("coil", 0, 4), ("coil", 4, 1), ("holding", 0, 1)]


# -- errors ---------------------------------------------------------------------


def test_modbus_exception_subclasses_are_reachable_by_type():
    """The typed subclasses this module branches on are the ones that arrive.

    `modbus_connection` translates a Modbus exception response through
    `ModbusExceptionError.from_code`, so a device answering exception code 0x01
    surfaces as `IllegalFunctionError` and 0x02 as `IllegalDataAddressError`
    regardless of backend. `async_identify` is built entirely on that mapping.
    """
    from modbus_connection import ModbusExceptionError

    assert isinstance(ModbusExceptionError.from_code(0x01, "x"), IllegalFunctionError)
    assert isinstance(ModbusExceptionError.from_code(0x02, "x"), IllegalDataAddressError)
