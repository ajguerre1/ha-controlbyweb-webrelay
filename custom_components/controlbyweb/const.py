"""Keys and defaults for the ControlByWeb integration.

The register map is NOT here -- it lives in `webrelay/const.py`, which has no
Home Assistant imports. This module holds only the strings Home Assistant stores
in a config entry, which must never change once released: an entry written by an
older version is read by a newer one.
"""

from __future__ import annotations

DOMAIN = "controlbyweb"

CONF_UNIT_ID = "unit_id"
"""Modbus unit id. Named `unit_id` rather than reusing Home Assistant's
`CONF_SLAVE`, which is the older spelling for the same thing."""

CONF_CONFIRM_PULSES = "confirm_pulses"
"""Whether a button press reads the coil back to prove the pulse happened."""

CONF_RELAYS = "relays"
"""Per-relay options, keyed by relay number as a STRING.

A string because config-entry options round-trip through JSON, which has no
integer keys -- an int written here comes back as a str, and code that indexed
with an int would silently find nothing.
"""

CONF_PULSE_SECONDS = "pulse_seconds"
CONF_RELAY_NAME = "name"

DEFAULT_CONFIRM_PULSES = True
