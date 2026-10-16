"""Daily forecast from the Open-Meteo Forecast API (Part B.2-B.3)."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from .http import DEFAULT_TIMEOUT, RetryPolicy, fetch_json
from .weather_codes import describe

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY_VARIABLES = ("weather_code", "temperature_2m_max", "temperature_2m_min",
                   "precipitation_sum", "wind_speed_10m_max")

# API field -> (column name, unit). The unit goes into the column name so a
# reader of the table never has to guess.
COLUMNS: dict[str, str] = {
    "temperature_2m_max": "Max temp (°C)",
    "temperature_2m_min": "Min temp (°C)",
    "precipitation_sum": "Precipitation (mm)",
    "wind_speed_10m_max": "Max wind (m/s)",
}


def validate_coordinates(lat: float, lon: float) -> None:
    """Raise ``ValueError`` for impossible coordinates before spending a request on them."""
    if not -90 <= lat <= 90:
        raise ValueError(f"Latitude must be between -90 and 90, got {lat}")
    if not -180 <= lon <= 180:
        raise ValueError(f"Longitude must be between -180 and 180, got {lon}")


def forecast_params(lat: float, lon: float, days: int, timezone: str = "auto") -> dict[str, Any]:
    """Query parameters for a daily forecast. Wind is requested in m/s to match MET Norway."""
    return {
        "latitude": round(lat, 4), "longitude": round(lon, 4),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": timezone,          # dates follow the location's local calendar day
        "forecast_days": days,
        "wind_speed_unit": "ms",
    }


def get_forecast(lat: float, lon: float, days: int = 7, *, timezone: str = "auto",
                 validate: bool = True, timeout: float = DEFAULT_TIMEOUT,
                 policy: RetryPolicy = RetryPolicy(), session: Any = None) -> dict[str, Any]:
    """Fetch the raw daily forecast JSON.

    Args:
        lat, lon: Decimal degrees.
        days: 1-16 (Open-Meteo's limit).
        timezone: IANA name or ``"auto"`` (resolve from coordinates), so that
            each row is a local calendar day rather than a UTC day.
        validate: Check inputs locally first. ``False`` lets the notebook show
            how the server itself rejects bad input.

    Raises:
        ValueError: invalid coordinates or ``days`` (only when ``validate``).
        WeatherAPIError: the request failed.
    """
    if validate:
        validate_coordinates(lat, lon)
        if not 1 <= days <= 16:
            raise ValueError("days must be between 1 and 16")
    payload, _ = fetch_json(FORECAST_URL, forecast_params(lat, lon, days, timezone),
                            timeout=timeout, policy=policy, session=session)
    return payload


def forecast_to_dataframe(payload: Mapping[str, Any]) -> pd.DataFrame:
    """Convert the forecast JSON into a tidy table indexed by local date.

    Missing variables become NaN columns instead of raising, so a partial
    response still renders. The weather code is decoded into words.
    """
    daily = payload.get("daily")
    if not daily or not daily.get("time"):
        raise ValueError("Forecast payload has no daily data")
    n = len(daily["time"])
    df = pd.DataFrame(index=pd.to_datetime(daily["time"]).rename("Date"))
    codes = daily.get("weather_code", [None] * n)
    df["Conditions"] = [describe(c) for c in codes]
    for key, column in COLUMNS.items():
        df[column] = pd.to_numeric(pd.Series(daily.get(key, [None] * n), index=df.index), errors="coerce")
    return df
