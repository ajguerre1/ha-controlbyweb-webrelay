"""Test doubles for a WebRelay-Quad.

READ THIS BEFORE TRUSTING A GREEN RUN.

`modbus_connection.mock` is a register store, not a device. It answers any
address it is given and models no behaviour at all. Everything this module adds
on top is **a claim about how a specific piece of hardware behaves**, and a claim
is only worth what measured it. So each one is listed here with the evidence
behind it, and anything the fake asserts that hardware has not confirmed is a bug
in the fake rather than a feature of it.

| Modelled here | Evidence |
|---|---|
| coils 0-3 readable, a fifth is `IllegalDataAddress` | survey of a live X-WR-4R3-E |
| holding registers `IllegalFunction` at every address | same survey, `0x0000`-`0x0027` |
| FC16 accepted at `0x0010`/`0x0012`/`0x0014`/`0x0016` | manual 3.3.4; pulses run on relay 4 |
| a pulse energises the coil, the DEVICE releases it | 3.0 s -> 3.31 s, 10.0 s -> 10.24 s |
| coil reads during a pulse do NOT cancel it | 139 reads inside pulses, 0 truncated |

What is NOT modelled, and must not be assumed by any test here: the ~50 s idle
connection timeout, the extend-on-repeated-pulse rule, and cancel-on-write during
a pulse. Tests that would depend on those belong in the hardware plan, not here.

The protocol package is placed on `sys.path` as a top-level `webrelay` rather
than reached through `custom_components.controlbyweb`. That is not a shortcut:
importing the parent package would execute
`custom_components/controlbyweb/__init__.py`, which imports Home Assistant and
therefore cannot run on Windows (`homeassistant.runner` imports POSIX-only
`fcntl`).

It also enforces the separation structurally. If a Home Assistant import is ever
added to `webrelay/`, this suite stops collecting rather than passing on a
technicality. Tests that genuinely need Home Assistant live in `tests/ha/`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "controlbyweb"

if str(_PACKAGE) not in sys.path:
    sys.path.insert(0, str(_PACKAGE))

#: Skip the Home Assistant suite wherever Home Assistant cannot be imported, rather than letting
#: it fail collection. Detected rather than keyed to the platform: what matters is whether the
#: dependency is installed. The whole directory is ignored because pytest loads a conftest before
#: it applies any file-level ignore, and `tests/ha/conftest.py` declares an HA plugin.
if importlib.util.find_spec("homeassistant") is None:
    collect_ignore = ["ha"]

from modbus_connection import IllegalDataAddressError, IllegalFunctionError
from modbus_connection.mock import (
    MockModbusConnection,
    MockModbusUnit,
    WriteEvent,
)

RELAY_COUNT = 4
UNIT_ID = 255


@pytest.fixture
def quad_unit() -> MockModbusUnit:
    """A mock unit configured to answer the way a real WebRelay-Quad answers.

    Note what is deliberately absent: writing a pulse register does NOT set the
    coil. The device does that; the mock does not, and pretending otherwise would
    let a test assert a pulse "worked" purely because the fake agreed with it.
    Tests that need an energised coil set `unit.coils` themselves, which keeps
    the stimulus visible in the test rather than hidden in a fixture.
    """
    unit = MockModbusConnection().for_unit(UNIT_ID)
    unit.coils = dict.fromkeys(range(RELAY_COUNT), False)

    # A fifth coil does not exist. `read_coils(4, 1)` is one of the three probes
    # that identify this device, so the fake has to get this exactly right or the
    # identification tests prove nothing.
    unit.fail_read(
        RELAY_COUNT,
        IllegalDataAddressError(f"no coil {RELAY_COUNT}"),
        register_type="coil",
    )

    # There is no holding-register space whatsoever -- not an empty one, not a
    # short one. This is the discriminating probe, because essentially every
    # other Modbus device has registers.
    for address in range(0x30):
        unit.fail_read(
            address,
            IllegalFunctionError("function code not supported"),
            register_type="holding",
        )

    return unit


@pytest.fixture
def writes(quad_unit: MockModbusUnit) -> list[WriteEvent]:
    """Every write reaching the device, in order, at wire level.

    A `WriteEvent` carries the function code, address and raw register values,
    so assertions can be made about the bytes on the wire rather than about the
    call that was intended.
    """
    recorded: list[WriteEvent] = []
    quad_unit.on_write(recorded.append)
    return recorded
