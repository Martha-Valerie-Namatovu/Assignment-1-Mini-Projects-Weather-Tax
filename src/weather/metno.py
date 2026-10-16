"""Second source: MET Norway Locationforecast 2.0 (Part C).

MET Norway's terms of service require a ``User-Agent`` that identifies the
application and gives a way to contact its owner. Requests with a generic or
missing User-Agent get HTTP 403. They also ask clients to truncate coordinates
to at most 4 decimals so that responses can be cached.
https://api.met.no/doc/TermsOfService
"""

from __future__ import annotations

import re
from typing import Any, Mapping

import pandas as pd

from .errors import ConfigurationError
from .http import DEFAULT_TIMEOUT, RetryPolicy, fetch_json
from .openmeteo import validate_coordinates

METNO_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
PLACEHOLDER_DOMAINS = ("example.com", "example.org")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def build_user_agent(app: str, contact_email: str) -> str:
    """Return ``"<app> <email>"`` after checking the email is real enough to send.

    Raises:
        ConfigurationError: the email is empty, malformed, or still the placeholder.
    """
    email = (contact_email or "").strip()
    if not _EMAIL.match(email):
        raise ConfigurationError(f"Contact email {email!r} is not a valid address. "
                                 "Set WEATHER_CONTACT_EMAIL or edit the config cell.")
    if email.lower().startswith("your.") or email.lower().endswith(PLACEHOLDER_DOMAINS):
        raise ConfigurationError("Contact email is still the placeholder. MET Norway requires real "
                                 "contact details; set WEATHER_CONTACT_EMAIL to your university email.")
    return f"{app} {email}"


def get_metno_forecast(lat: float, lon: float, user_agent: str, *, timeout: float = DEFAULT_TIMEOUT,
                       policy: RetryPolicy = RetryPolicy(), session: Any = None) -> dict[str, Any]:
    """Fetch the compact Locationforecast JSON. Coordinates are truncated to 4 decimals."""
    validate_coordinates(lat, lon)
    params = {"lat": f"{lat:.4f}", "lon": f"{lon:.4f}"}
    payload, _ = fetch_json(METNO_URL, params, headers={"User-Agent": user_agent},
                            timeout=timeout, policy=policy, session=session)
    return payload


def _step_precipitation(entry: Mapping[str, Any], step_hours: float) -> float | None:
    """Precipitation for the interval starting at ``entry``, without double counting.

    Near-term entries are hourly and carry both ``next_1_hours`` and
    ``next_6_hours``; summing both would count the same rain several times.
    Later entries are 6-hourly and carry only ``next_6_hours``. So read the
    window that matches the gap to the next timestamp.
    """
    window = "next_1_hours" if step_hours <= 1 else "next_6_hours"
    value = entry["data"].get(window, {}).get("details", {}).get("precipitation_amount")
    return None if value is None else float(value)


def metno_to_daily(payload: Mapping[str, Any], timezone: str) -> pd.DataFrame:
    """Aggregate the time series into local calendar days.

    Columns match ``forecast_to_dataframe`` (max/min temperature, precipitation
    sum, max wind) plus ``Hours covered``. Each interval is credited to the
    local day in which it starts, so in Kampala (UTC+3) the 6-hour window from
    21:00 to 03:00 counts towards the earlier day; a day can therefore show
    slightly more or less than 24 hours. Days with less than 24 hours covered
    (normally the first and last) are partial and should not be compared
    like-for-like.
    """
    series = payload.get("properties", {}).get("timeseries") or []
    if not series:
        raise ValueError("MET Norway payload has no timeseries")
    times = pd.to_datetime([e["time"] for e in series], utc=True)
    rows = []
    for i, entry in enumerate(series):
        if i + 1 < len(series):
            step = (times[i + 1] - times[i]).total_seconds() / 3600
        else:  # last entry: assume the same spacing as the one before it
            step = (times[i] - times[i - 1]).total_seconds() / 3600 if i else 1.0
        instant = entry["data"]["instant"]["details"]
        rows.append({
            "time": times[i],
            "temp": instant.get("air_temperature"),
            "wind": instant.get("wind_speed"),
            "precip": _step_precipitation(entry, step),
            "hours": step,
        })
    df = pd.DataFrame(rows)
    df["Date"] = df["time"].dt.tz_convert(timezone).dt.tz_localize(None).dt.normalize()
    daily = df.groupby("Date").agg(**{
        "Max temp (°C)": ("temp", "max"),
        "Min temp (°C)": ("temp", "min"),
        "Precipitation (mm)": ("precip", lambda s: s.sum(min_count=1)),
        "Max wind (m/s)": ("wind", "max"),
        "Hours covered": ("hours", "sum"),
    })
    return daily
