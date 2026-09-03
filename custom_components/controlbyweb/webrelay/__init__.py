"""The WebRelay-Quad protocol layer, free of Home Assistant imports.

Kept separate so it can be tested on a machine where Home Assistant cannot be
imported at all, and so that contributing this integration to Home Assistant core
-- which requires protocol code to live in a published library -- would be a move
rather than a rewrite.
"""

from .const import (
    DEFAULT_PORT,
    DEFAULT_PULSE_SECONDS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    MAX_SCAN_INTERVAL,
    PULSE_MAX_SECONDS,
    PULSE_MIN_SECONDS,
    PULSE_REGISTERS,
    RELAY_COUNT,
)
from .device import WebRelayQuad, encode_pulse
from .errors import NotAWebRelayQuadError, PulseDurationError, WebRelayError

__all__ = [
    "DEFAULT_PORT",
    "DEFAULT_PULSE_SECONDS",
    "DEFAULT_SCAN_INTERVAL",
    "DEFAULT_UNIT_ID",
    "MAX_SCAN_INTERVAL",
    "PULSE_MAX_SECONDS",
    "PULSE_MIN_SECONDS",
    "PULSE_REGISTERS",
    "RELAY_COUNT",
    "NotAWebRelayQuadError",
    "PulseDurationError",
    "WebRelayError",
    "WebRelayQuad",
    "encode_pulse",
]
