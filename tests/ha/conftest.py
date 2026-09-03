"""Fixtures for the Home Assistant half of the suite.

These run in CI only. Home Assistant cannot be imported on Windows
(`homeassistant.runner` imports POSIX-only `fcntl`), and the top-level conftest
skips this directory wherever it is not installed.

The Modbus unit is replaced, not the device: `async_get_unit` is patched to hand
back the same `MockModbusUnit` the offline suite uses, so entity behaviour is
asserted against the same wire-level double rather than against a second,
divergent fake. A second fake is how two descriptions of one device drift apart.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from modbus_connection.mock import MockModbusUnit
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.controlbyweb.const import (
    CONF_CONFIRM_PULSES,
    CONF_PULSE_SECONDS,
    CONF_RELAYS,
    CONF_UNIT_ID,
    DOMAIN,
)

# No `pytest_plugins` declaration here. pytest refuses it in a non-root conftest, and it is
# unnecessary anyway: pytest-homeassistant-custom-component registers itself through entry points
# when installed, which is exactly the condition tests/conftest.py already tests to decide whether
# to collect this directory at all.

#: A documentation-range address (RFC 5737). Not a real one -- a test that quietly reached a real
#: relay board would be a very bad way to find out the mock was not wired in.
ENTRY_DATA = {CONF_HOST: "192.0.2.10", CONF_PORT: 502, CONF_UNIT_ID: 255}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Home Assistant will not load a custom component in tests without this."""
    return


@pytest.fixture
def entry_options() -> dict:
    """Options with a confirmable pulse length on every relay.

    1.5 s deliberately: it is the device's own factory default, it is above
    `MIN_CONFIRMABLE_SECONDS`, and it is one of the two durations a real
    installation uses.
    """
    return {
        CONF_RELAYS: {str(relay): {CONF_PULSE_SECONDS: 1.5} for relay in range(1, 5)},
        CONF_CONFIRM_PULSES: True,
    }


@pytest.fixture
async def setup_entry(hass: HomeAssistant, quad_unit: MockModbusUnit, entry_options):
    """Set up the integration against the mock unit, and hand both back."""

    async def _setup(options: dict | None = None) -> MockConfigEntry:
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=ENTRY_DATA,
            options=entry_options if options is None else options,
            unique_id="192.0.2.10:502:255",
            title="WebRelay-Quad",
        )
        entry.add_to_hass(hass)

        with patch("custom_components.controlbyweb.async_get_unit", return_value=quad_unit):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
        return entry

    return _setup
