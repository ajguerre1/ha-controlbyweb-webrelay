"""The WebRelay-Quad's Modbus map, taken from manual rev 2.5 section 3.3.

Everything here was also confirmed against a live X-WR-4R3-E, because a manual
describes a product line and this addresses one device.
"""

from __future__ import annotations

RELAY_COUNT = 4
"""Relays on a WebRelay-Quad. Also the exact size of its coil space -- reading a
fifth coil is an illegal data address, which is half of how the device is
identified (see `WebRelayQuad.async_identify`)."""

COIL_BASE = 0x0000
"""Relay 1 is coil 0x0000, relay 4 is coil 0x0003 (section 3.3.1)."""

PULSE_REGISTERS: tuple[int, ...] = (0x0010, 0x0012, 0x0014, 0x0016)
"""Write-multiple-registers targets, one per relay (section 3.3.4).

Two registers each, and WRITE-ONLY: the device implements no register-read
function code at all, so nothing here can be read back to confirm a write.
"""

PULSE_MIN_SECONDS = 0.1
PULSE_MAX_SECONDS = 86400.0
"""Section 3.3.4. The device CLAMPS out-of-range values rather than rejecting
them, so a typo would otherwise become a silently different pulse. This module
raises instead."""

DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 255
"""Section 3.3 specifies unit id 255. Unit 1 is also tolerated by this hardware,
but 255 is what the manual says and what the device's own examples use."""

DEFAULT_PULSE_SECONDS = 1.0
"""Deliberately short. This value cannot be read from the device (there is no
register-read function code), so it is a guess until someone matches it to the
`Pulse Duration` field on the device's own setup page. A pulse that is too short
fails to open something; one that is too long holds a relay closed."""

DEFAULT_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 45
"""Section 3.3: an idle Modbus connection is dropped after "about 50 seconds".
The poll is therefore what holds the socket open, and a slower one does not
reduce load so much as make the next command pay a reconnect first. 45 leaves
margin under 50."""
