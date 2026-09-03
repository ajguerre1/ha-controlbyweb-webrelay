"""The pulse duration encoding, pinned against three independent authorities.

This encoding is the one place where being subtly wrong produces a working
command with the wrong behaviour: the device accepts any two registers and pulses
for whatever they decode to. A byte order mistake would not raise, it would just
hold a gate open for a different length of time. So it is pinned three ways --
the manual's own worked example, the values a working installation already sends,
and the Modbus library's independent implementation.
"""

from __future__ import annotations

import struct

import pytest
from modbus_connection.encode import encode_float32
from webrelay import PulseDurationError, encode_pulse


def test_manual_worked_example():
    """Manual rev 2.5 section 3.3.4 shows 10 seconds transmitted as `00 00 41 20`."""
    assert encode_pulse(10.0) == [0x0000, 0x4120]


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (10.0, [0, 16672]),  # the manual's example, in decimal
        (3.0, [0, 16448]),
        (1.5, [0, 16320]),
    ],
)
def test_values_a_working_installation_already_sends(seconds, expected):
    """Byte-identical to what the YAML `modbus.write_register` calls send today.

    Those durations were read off the device rather than chosen, and they DIFFER
    per relay. Producing a "tidier" uniform value here would change behaviour on
    real hardware while every test still passed, so the exact register lists are
    pinned rather than the round trip.
    """
    assert encode_pulse(seconds) == expected


@pytest.mark.parametrize("seconds", [0.1, 0.5, 1.0, 1.5, 3.0, 10.0, 60.0, 86400.0])
def test_agrees_with_the_library_primitive(seconds):
    """`encode_pulse` is hand-written; this proves it is not independently wrong.

    `modbus_connection.encode.encode_float32` with a little word order is the
    same transformation. It is not used at runtime -- it lives in a submodule the
    package does not re-export and it cannot enforce the device's range -- but
    disagreeing with it would mean one of the two is broken.
    """
    assert encode_pulse(seconds) == encode_float32(seconds, word_order="little")


@pytest.mark.parametrize("seconds", [0.1, 1.5, 3.0, 86400.0])
def test_round_trips_through_the_documented_wire_order(seconds):
    """Decoding the registers as the manual describes returns the input.

    ABCD sent as CDAB: reassembling the transmitted words in reverse gives back
    the original big-endian float.
    """
    low, high = encode_pulse(seconds)
    assert struct.unpack(">f", struct.pack(">HH", high, low))[0] == pytest.approx(seconds)


@pytest.mark.parametrize("seconds", [0.0, 0.09, -1.0, 86400.1, 1e9])
def test_rejects_what_the_device_would_silently_clamp(seconds):
    """Out of range raises here rather than being quietly changed on the device.

    Section 3.3.4: a value below 0.1 becomes 0.1 and one above 86400 becomes
    86400. The device reports success either way, so a misplaced decimal point
    would otherwise be invisible.
    """
    with pytest.raises(PulseDurationError):
        encode_pulse(seconds)


def test_accepts_the_exact_boundaries():
    """0.1 and 86400 are valid; the rejection above must not be off by one step."""
    assert encode_pulse(0.1)
    assert encode_pulse(86400.0)
