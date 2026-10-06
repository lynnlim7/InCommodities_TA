"""
Errors raised by power position domain.
"""

class PositionError(Exception):
    """Base error for position calculation failures."""

class UnsupportedAreaError(PositionError):
    """Trade references an unsupported area."""

class UnsupportedTradeTypeError(PositionError):
    """Trader references an unsupported trade type."""

class UnsupportedProfileError(PositionError):
    """Trade references an unsupported load profile."""

class InvalidProfileError(PositionError):
    """Load profile configuration is invalid."""

class PositionCalculationError(PositionError):
    """Position cannot be calculated for the requested period."""