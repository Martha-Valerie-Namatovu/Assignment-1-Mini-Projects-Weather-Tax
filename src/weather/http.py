"""HTTP helpers: a bare ``urllib`` call (Part A) and a robust ``requests`` wrapper (Part C).

``fetch_json`` is the single entry point every API call in the project goes
through. It sets a timeout, calls ``raise_for_status()``, retries transient
failures with capped exponential backoff, and raises ``WeatherAPIError`` when it
finally gives up.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import requests

from .errors import WeatherAPIError

DEFAULT_TIMEOUT = 10.0  # seconds; generous for East African mobile links, short enough to fail fast


@dataclass(frozen=True)
class ResponseInfo:
    """What Part A asks us to report about one request."""

    url: str
    status: int
    content_type: str
    elapsed_ms: float

    def __str__(self) -> str:
        return f"HTTP {self.status} | {self.content_type} | {self.elapsed_ms:.0f} ms | {self.url}"


@dataclass(frozen=True)
class RetryPolicy:
    """When and how long to wait before retrying.

    Delay before retry *n* (1-based) is ``min(cap, base * 2**(n-1))``: 0.5 s, 1 s, 2 s, ...
    Only failures that may succeed on a second try are retried: connection
    errors, timeouts, HTTP 429 and 5xx. A 4xx means our request is wrong, so
    repeating it would only add load.
    """

    max_retries: int = 3
    backoff_base: float = 0.5
    backoff_cap: float = 8.0
    retry_statuses: frozenset[int] = field(default_factory=lambda: frozenset({429, 500, 502, 503, 504}))

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if self.backoff_base < 0 or self.backoff_cap < 0:
            raise ValueError("backoff values must be >= 0")

    def delay(self, retry_number: int) -> float:
        """Seconds to wait before the given retry (1 = first retry)."""
        return min(self.backoff_cap, self.backoff_base * 2 ** (retry_number - 1))


def urllib_get_json(url: str, params: Mapping[str, Any], timeout: float = DEFAULT_TIMEOUT,
                    headers: Mapping[str, str] | None = None) -> tuple[dict[str, Any], ResponseInfo]:
    """GET ``url`` with only the standard library and decode the JSON body.

    The query string is built with ``urllib.parse.urlencode``. Non-2xx responses
    surface as ``urllib.error.HTTPError``; the caller handles them.
    """
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(full_url, headers=dict(headers or {}))
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        info = ResponseInfo(full_url, response.status, response.headers.get("Content-Type", ""),
                            (time.perf_counter() - start) * 1000)
    return json.loads(raw.decode(charset)), info


def _server_reason(response: requests.Response) -> str | None:
    """Pull an explanation out of an error body, if the API sent one."""
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        return body.get("reason") or body.get("message")
    return None


def fetch_json(url: str, params: Mapping[str, Any] | None = None, *,
               headers: Mapping[str, str] | None = None,
               timeout: float = DEFAULT_TIMEOUT,
               policy: RetryPolicy = RetryPolicy(),
               session: requests.Session | None = None,
               sleep: Callable[[float], None] = time.sleep,
               log: Callable[[str], None] | None = None) -> tuple[Any, ResponseInfo]:
    """GET ``url`` and return ``(decoded_json, ResponseInfo)``, retrying transient failures.

    Args:
        url: Endpoint without query string.
        params: Query parameters, encoded by ``requests``.
        headers: Extra headers, e.g. ``User-Agent`` for MET Norway.
        timeout: Seconds for connect and read. Must be positive.
        policy: Retry policy (attempts = ``policy.max_retries + 1``).
        session: A ``requests.Session``, or any object with a compatible ``get``.
            Tests pass a fake here to simulate an outage without a network.
        sleep: Injected so tests can record backoff delays instead of waiting.
        log: Optional callback receiving one line per failed attempt.

    Raises:
        ValueError: ``timeout`` is not positive.
        WeatherAPIError: a non-retryable HTTP error, an undecodable body, or retries exhausted.
    """
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    http = session or requests.Session()
    attempts = policy.max_retries + 1
    last_error = "unknown error"
    last_status: int | None = None
    for attempt in range(1, attempts + 1):
        start = time.perf_counter()
        try:
            response = http.get(url, params=params, headers=dict(headers or {}), timeout=timeout)
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            reason = _server_reason(exc.response) if exc.response is not None else None
            if status not in policy.retry_statuses:
                raise WeatherAPIError(f"HTTP {status} from {url}: {reason or exc}", url=url,
                                      status=status, attempts=attempt, reason=reason) from exc
            last_status, last_error = status, f"HTTP {status}"
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_status, last_error = None, f"{type(exc).__name__}: {exc}"
        else:
            info = ResponseInfo(response.url, response.status_code,
                                response.headers.get("Content-Type", ""),
                                (time.perf_counter() - start) * 1000)
            try:
                return response.json(), info
            except ValueError as exc:
                raise WeatherAPIError(f"Response from {url} is not valid JSON", url=url,
                                      status=response.status_code, attempts=attempt) from exc
        if attempt < attempts:
            wait = policy.delay(attempt)
            if log:
                log(f"attempt {attempt}/{attempts} failed ({last_error}); retrying in {wait:.2f} s")
            sleep(wait)
        elif log:
            log(f"attempt {attempt}/{attempts} failed ({last_error}); giving up")
    raise WeatherAPIError(f"Gave up on {url} after {attempts} attempts: {last_error}",
                          url=url, status=last_status, attempts=attempts)
