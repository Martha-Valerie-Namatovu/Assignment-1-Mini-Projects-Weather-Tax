"""Offline tests for the weather parsing and HTTP-retry code, using saved sample JSON."""

import pandas as pd
import pytest
import requests

from src.weather import (ConfigurationError, Location, RetryPolicy, WeatherAPIError, build_user_agent,
                         choose_location, compare_sources, describe, fetch_json, forecast_to_dataframe,
                         metno_to_daily, parse_geocoding, validate_coordinates)


# ---------------------------------------------------------------- geocoding parsing
def test_parse_geocoding_kampala_best_match_is_uganda(sample):
    locs = parse_geocoding(sample("geocode_kampala"))
    assert locs[0].country == "Uganda"
    assert locs[0].timezone == "Africa/Kampala"
    assert locs[0].latitude == pytest.approx(0.31628)
    assert all(isinstance(l, Location) for l in locs)


def test_parse_geocoding_missing_results_key_gives_empty_list(sample):
    payload = sample("geocode_no_results")
    assert "results" not in payload            # the API really omits the key
    assert parse_geocoding(payload) == []


def test_springfield_is_ambiguous_and_labels_tell_candidates_apart(sample):
    locs = parse_geocoding(sample("geocode_springfield"))
    assert len(locs) > 1
    assert len({l.label for l in locs}) == len(locs)


def test_choose_location_reprompts_on_bad_input(sample):
    locs = parse_geocoding(sample("geocode_springfield"))
    answers = iter(["", "abc", "99", "2"])
    picked = choose_location(locs, input_fn=lambda _: next(answers), print_fn=lambda _: None)
    assert picked == locs[1]


def test_choose_location_preset_choice_and_single_candidate(sample):
    locs = parse_geocoding(sample("geocode_kampala"))
    assert choose_location(locs, choice=1) == locs[0]
    assert choose_location(locs[:1], input_fn=lambda _: pytest.fail("should not prompt")) == locs[0]
    with pytest.raises(ValueError):
        choose_location(locs, choice=0)


# ---------------------------------------------------------------- forecast parsing
def test_forecast_dataframe_has_units_and_decoded_conditions(sample):
    df = forecast_to_dataframe(sample("forecast_kampala"))
    assert list(df.columns) == ["Conditions", "Max temp (°C)", "Min temp (°C)", "Precipitation (mm)",
                                "Max wind (m/s)"]
    assert len(df) == 7
    assert isinstance(df.index, pd.DatetimeIndex)
    assert (df["Max temp (°C)"] >= df["Min temp (°C)"]).all()
    assert "Unknown" not in " ".join(df["Conditions"])


def test_forecast_dataframe_tolerates_missing_variable(sample):
    payload = sample("forecast_kampala")
    del payload["daily"]["wind_speed_10m_max"]
    df = forecast_to_dataframe(payload)
    assert df["Max wind (m/s)"].isna().all()


def test_forecast_dataframe_rejects_empty_payload():
    with pytest.raises(ValueError):
        forecast_to_dataframe({"daily": {"time": []}})


def test_weather_code_descriptions():
    assert describe(0) == "Clear sky"
    assert describe(95.0) == "Thunderstorm"
    assert describe(None) == "No data"
    assert describe(42).startswith("Unknown")


# ---------------------------------------------------------------- MET Norway parsing
def test_metno_daily_aggregation_is_local_and_not_double_counted(sample):
    payload = sample("metno_kampala")
    daily = metno_to_daily(payload, "Africa/Kampala")
    assert (daily["Max temp (°C)"] >= daily["Min temp (°C)"]).all()
    # Summing every next_1_hours AND next_6_hours value would inflate the total;
    # our total must equal the sum over non-overlapping windows only.
    series = payload["properties"]["timeseries"]
    naive_total = sum(e["data"].get(k, {}).get("details", {}).get("precipitation_amount", 0)
                      for e in series for k in ("next_1_hours", "next_6_hours"))
    assert daily["Precipitation (mm)"].sum() < naive_total
    # The first UTC timestamp is 00:00Z = 03:00 in Kampala, so day 1 is partial.
    assert daily["Hours covered"].iloc[0] < 24


def test_compare_sources_uses_only_fully_covered_days(sample):
    om = forecast_to_dataframe(sample("forecast_kampala"))
    met = metno_to_daily(sample("metno_kampala"), "Africa/Kampala")
    table = compare_sources(om, met)
    assert om.index[0] not in table.index      # partial first MET day excluded
    assert ("Difference", "Max temp (°C)") in table.columns


def test_invalid_latitude_sample_matches_local_validation(sample):
    assert sample("forecast_invalid_latitude")["error"] is True
    with pytest.raises(ValueError):
        validate_coordinates(95, 32.5)


# ---------------------------------------------------------------- user agent
@pytest.mark.parametrize("email", ["", "not-an-email", "your.name@ucu.ac.ug", "someone@example.com"])
def test_user_agent_rejects_placeholder_or_invalid_email(email):
    with pytest.raises(ConfigurationError):
        build_user_agent("app/1.0", email)


def test_user_agent_contains_app_and_email():
    assert build_user_agent("app/1.0", "s.student@stud.ucu.ac.ug") == "app/1.0 s.student@stud.ucu.ac.ug"


# ---------------------------------------------------------------- retry behaviour (fake session)
class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}
        self.url, self.headers = "https://fake", {"Content-Type": "application/json"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)

    def json(self):
        return self._body


class FakeSession:
    """Returns (or raises) the scripted outcomes in order and counts calls."""

    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    def get(self, url, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_retries_5xx_then_succeeds_with_exponential_backoff():
    session = FakeSession([FakeResponse(503), requests.ConnectionError("down"), FakeResponse(200, {"ok": 1})])
    waits = []
    data, info = fetch_json("https://fake", session=session, sleep=waits.append,
                            policy=RetryPolicy(max_retries=3, backoff_base=0.5))
    assert data == {"ok": 1} and info.status == 200
    assert waits == [0.5, 1.0]


def test_gives_up_after_retry_cap_with_custom_exception():
    session = FakeSession([requests.Timeout("slow")] * 4)
    with pytest.raises(WeatherAPIError) as err:
        fetch_json("https://fake", session=session, sleep=lambda s: None, policy=RetryPolicy(max_retries=3))
    assert session.calls == 4 and err.value.attempts == 4


def test_client_error_is_not_retried_and_keeps_server_reason(sample):
    session = FakeSession([FakeResponse(400, sample("forecast_invalid_latitude"))])
    with pytest.raises(WeatherAPIError) as err:
        fetch_json("https://fake", session=session, sleep=lambda s: pytest.fail("must not retry"))
    assert session.calls == 1
    assert err.value.status == 400 and "Latitude" in err.value.reason


def test_backoff_is_capped():
    policy = RetryPolicy(backoff_base=1, backoff_cap=5)
    assert [policy.delay(n) for n in range(1, 6)] == [1, 2, 4, 5, 5]


def test_non_positive_timeout_rejected():
    with pytest.raises(ValueError):
        fetch_json("https://fake", timeout=0)
