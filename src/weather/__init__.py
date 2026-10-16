"""Mini-project 1: geocode a place, fetch its forecast from two open APIs, display it."""

from .display import compare_sources, format_table, plot_forecast, summarise
from .errors import ConfigurationError, LocationNotFoundError, WeatherAPIError, WeatherError
from .geocoding import Location, choose_location, geocode, parse_geocoding
from .http import ResponseInfo, RetryPolicy, fetch_json, urllib_get_json
from .metno import build_user_agent, get_metno_forecast, metno_to_daily
from .openmeteo import forecast_to_dataframe, get_forecast, validate_coordinates
from .weather_codes import WMO_CODES, describe

__all__ = [
    "ConfigurationError", "Location", "LocationNotFoundError", "ResponseInfo", "RetryPolicy",
    "WMO_CODES", "WeatherAPIError", "WeatherError", "build_user_agent", "choose_location",
    "compare_sources", "describe", "fetch_json", "forecast_to_dataframe", "format_table",
    "geocode", "get_forecast", "get_metno_forecast", "metno_to_daily", "parse_geocoding",
    "plot_forecast", "summarise", "urllib_get_json", "validate_coordinates",
]
