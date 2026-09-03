"""Errors raised by the WebRelay protocol layer.

These deliberately do not inherit from anything in Home Assistant -- this package
has no Home Assistant imports, which is what lets it be tested off-HA and is what
would be lifted to PyPI if this integration were ever contributed to core.
"""

from __future__ import annotations


class WebRelayError(Exception):
    """Base class for every error this package raises."""


class NotAWebRelayQuadError(WebRelayError):
    """The device at this address is not a WebRelay-Quad.

    Raised by identification rather than discovered later, because this
    integration WRITES: an unrecognised device would otherwise receive
    function-code 16 writes into a register map that means something else.
    """


class PulseDurationError(WebRelayError, ValueError):
    """A pulse duration outside the device's 0.1-86400 s range.

    Raised rather than clamped. The device itself clamps silently, which turns a
    misplaced decimal point into a working command with the wrong behaviour.
    """
