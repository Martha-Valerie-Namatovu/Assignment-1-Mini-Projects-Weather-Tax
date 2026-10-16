"""Exception hierarchy for the weather client.

Every failure the notebook can meet is one of these, so callers can catch
``WeatherError`` once, or a subclass when they want to react differently.
"""

from __future__ import annotations


class WeatherError(Exception):
    """Base class for all weather-client errors."""


class ConfigurationError(WeatherError):
    """The client was configured wrongly, e.g. a placeholder contact email."""


class LocationNotFoundError(WeatherError):
    """Geocoding returned no candidates for the requested name."""

    def __init__(self, name: str) -> None:
        super().__init__(f"No location found for {name!r}. Check the spelling or try a larger nearby town.")
        self.name = name


class WeatherAPIError(WeatherError):
    """A request failed for good: a 4xx response, or retries were exhausted.

    Attributes:
        url: The URL that was requested (without query string).
        status: HTTP status of the last response, or ``None`` if no response arrived.
        attempts: How many attempts were made in total.
        reason: The server's explanation when it gave one (Open-Meteo sends ``{"reason": ...}``).
    """

    def __init__(self, message: str, *, url: str, status: int | None = None,
                 attempts: int = 1, reason: str | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.status = status
        self.attempts = attempts
        self.reason = reason
