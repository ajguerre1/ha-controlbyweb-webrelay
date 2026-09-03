"""What a fresh install actually creates, and what it deliberately does not."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.const import CONF_SCAN_INTERVAL, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from modbus_connection.mock import MockModbusUnit

from custom_components.controlbyweb.const import DOMAIN
from custom_components.controlbyweb.webrelay import MAX_SCAN_INTERVAL


async def test_creates_a_sensor_and_a_button_for_every_relay(
    hass: HomeAssistant, quad_unit: MockModbusUnit, setup_entry
):
    """Four relays, four state sensors, four pulse buttons."""
    entry = await setup_entry()
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)

    by_domain: dict[str, int] = {}
    for entity in entities:
        by_domain[entity.domain] = by_domain.get(entity.domain, 0) + 1

    assert by_domain == {"binary_sensor": 4, "button": 4, "switch": 4}


async def test_the_latching_switches_are_created_but_switched_off(
    hass: HomeAssistant, quad_unit: MockModbusUnit, setup_entry
):
    """The switches exist in the registry and have no state until enabled.

    This is the safety property, so it is asserted rather than assumed: on a
    board wired to a gate release, an enabled latching switch is one accidental
    tap away from holding the gate relay closed.
    """
    entry = await setup_entry()
    registry = er.async_get(hass)

    switches = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "switch"
    ]

    assert len(switches) == 4
    assert all(e.disabled_by is er.RegistryEntryDisabler.INTEGRATION for e in switches)
    # Disabled entities have no state object at all, which is what keeps them
    # off dashboards and out of reach of a stray service call.
    assert all(hass.states.get(e.entity_id) is None for e in switches)


async def test_relay_states_come_from_one_read(
    hass: HomeAssistant, quad_unit: MockModbusUnit, setup_entry
):
    """All four sensors reflect the coils, and only one request was made."""
    quad_unit.coils = {0: False, 1: True, 2: False, 3: True}

    entry = await setup_entry()
    registry = er.async_get(hass)

    states = []
    for relay in range(1, 5):
        entity_id = registry.async_get_entity_id(
            "binary_sensor", DOMAIN, f"{entry.entry_id}_{relay}_state"
        )
        states.append(hass.states.get(entity_id).state)

    assert states == [STATE_OFF, STATE_ON, STATE_OFF, STATE_ON]

    coil_reads = [e for e in quad_unit.read_events if e.register_type == "coil"]
    assert len(coil_reads) == 1
    assert (coil_reads[0].address, coil_reads[0].count) == (0, 4)


async def test_relay_names_come_from_the_options(
    hass: HomeAssistant, quad_unit: MockModbusUnit, setup_entry, entry_options
):
    """A named relay reads as its name; an unnamed one falls back to its number."""
    from custom_components.controlbyweb.const import (
        CONF_PULSE_SECONDS,
        CONF_RELAY_NAME,
        CONF_RELAYS,
    )

    entry = await setup_entry(
        {
            **entry_options,
            CONF_RELAYS: {
                "1": {CONF_PULSE_SECONDS: 3.0, CONF_RELAY_NAME: "Front door"},
                "2": {CONF_PULSE_SECONDS: 1.5},
            },
        }
    )
    registry = er.async_get(hass)

    named = registry.async_get_entity_id("binary_sensor", DOMAIN, f"{entry.entry_id}_1_state")
    unnamed = registry.async_get_entity_id("binary_sensor", DOMAIN, f"{entry.entry_id}_2_state")

    assert "Front door" in hass.states.get(named).name
    assert "2" in hass.states.get(unnamed).name


@pytest.mark.parametrize(
    ("configured", "expected"),
    [(10, 10), (45, 45), (120, MAX_SCAN_INTERVAL), (0, 1)],
)
async def test_the_scan_interval_is_clamped_below_the_connection_timeout(
    hass: HomeAssistant,
    quad_unit: MockModbusUnit,
    setup_entry,
    entry_options,
    configured,
    expected,
):
    """The board drops an idle connection after ~50 s, so 45 is a ceiling.

    Clamped rather than rejected. An entry written before this ceiling existed,
    or edited by hand, must not be able to set an interval that quietly makes
    every button press reconnect first.
    """
    entry = await setup_entry({**entry_options, CONF_SCAN_INTERVAL: configured})

    assert entry.runtime_data.update_interval == timedelta(seconds=expected)


async def test_unload_leaves_nothing_behind(
    hass: HomeAssistant, quad_unit: MockModbusUnit, setup_entry
):
    """Unloading removes every entity state, so a reload is a clean start."""
    entry = await setup_entry()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert all(hass.states.get(e.entity_id) is None for e in entities)
