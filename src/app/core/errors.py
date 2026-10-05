"""Domain invariant violations.

Every domain error subclasses ``ValueError`` so that Pydantic validators at the input
boundary capture them automatically and surface them as field-level validation errors,
rather than each invariant having to be restated in the parsing layer.
"""

from __future__ import annotations


class DomainError(ValueError):
    """Base class for a violated domain invariant."""


class InvalidIntervalError(DomainError):
    """A delivery or reporting interval is empty or inverted."""


class InvalidVolumeError(DomainError):
    """A trade volume is not strictly positive."""


class InvalidPriceError(DomainError):
    """A trade price is not strictly positive."""


class MissingValueError(DomainError):
    """A required text field is empty."""


class UnsupportedDirectionError(DomainError):
    """A buy/sell value is not a recognised trade direction."""


class UnsupportedLoadProfileError(DomainError):
    """A load profile has no registered covered-hour rule."""


class UnsupportedTradeTypeError(DomainError):
    """A trade type is not recognised by the application configuration."""


class DuplicateTradeIdError(DomainError):
    """Two trades in one book share a trade_id."""
