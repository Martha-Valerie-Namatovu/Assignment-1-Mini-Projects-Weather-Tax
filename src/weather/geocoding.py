"""Location name -> coordinates via the Open-Meteo Geocoding API (Part B.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .errors import LocationNotFoundError
from .http import DEFAULT_TIMEOUT, RetryPolicy, fetch_json

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


@dataclass(frozen=True)
class Location:
    """One geocoding candidate."""

    name: str
    latitude: float
    longitude: float
    country: str = ""
    admin1: str = ""
    timezone: str = "auto"
    population: int | None = None

    @property
    def label(self) -> str:
        """Human-readable name that tells candidates apart, e.g. 'Springfield, Illinois, United States'."""
        return ", ".join(p for p in (self.name, self.admin1, self.country) if p)

    def __str__(self) -> str:
        pop = f", pop. {self.population:,}" if self.population else ""
        return f"{self.label} ({self.latitude:.4f}, {self.longitude:.4f}{pop})"


def parse_geocoding(payload: Mapping[str, Any]) -> list[Location]:
    """Turn a geocoding JSON payload into ``Location`` objects.

    Open-Meteo omits the ``results`` key entirely when nothing matches, so a
    missing key yields an empty list rather than a ``KeyError``.
    """
    locations = []
    for item in payload.get("results") or []:
        locations.append(Location(
            name=item["name"],
            latitude=float(item["latitude"]),
            longitude=float(item["longitude"]),
            country=item.get("country", ""),
            admin1=item.get("admin1", ""),
            timezone=item.get("timezone", "auto"),
            population=item.get("population"),
        ))
    return locations


def geocode(name: str, count: int = 10, *, timeout: float = DEFAULT_TIMEOUT,
            policy: RetryPolicy = RetryPolicy(), session: Any = None) -> list[Location]:
    """Return candidate locations for ``name``, best match first.

    Raises:
        ValueError: ``name`` is blank or ``count`` is outside 1-100.
        LocationNotFoundError: the API knows no place with that name.
        WeatherAPIError: the request itself failed.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Location name must not be empty")
    if not 1 <= count <= 100:
        raise ValueError("count must be between 1 and 100")
    payload, _ = fetch_json(GEOCODING_URL, {"name": name, "count": count, "language": "en", "format": "json"},
                            timeout=timeout, policy=policy, session=session)
    candidates = parse_geocoding(payload)
    if not candidates:
        raise LocationNotFoundError(name)
    return candidates


def choose_location(candidates: Sequence[Location], choice: int | None = None,
                    input_fn: Callable[[str], str] = input,
                    print_fn: Callable[[str], None] = print) -> Location:
    """Pick one candidate, asking the user when the name is ambiguous.

    Args:
        candidates: Output of ``geocode``.
        choice: 1-based index chosen in advance (e.g. from the config cell). If given,
            no prompt is shown, which keeps "Restart & Run All" non-interactive.
        input_fn: Prompt function; tests and the notebook demo pass a scripted one.
        print_fn: Where the numbered list goes.

    A single candidate is returned without asking. Invalid answers re-prompt.
    """
    if not candidates:
        raise ValueError("No candidates to choose from")
    if choice is not None:
        if not 1 <= choice <= len(candidates):
            raise ValueError(f"choice must be between 1 and {len(candidates)}")
        return candidates[choice - 1]
    if len(candidates) == 1:
        return candidates[0]
    print_fn(f"{len(candidates)} places match. Pick one:")
    for i, loc in enumerate(candidates, start=1):
        print_fn(f"  {i}. {loc}")
    while True:
        answer = input_fn(f"Number (1-{len(candidates)}): ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(candidates):
            return candidates[int(answer) - 1]
        print_fn(f"  {answer!r} is not a number between 1 and {len(candidates)}.")
