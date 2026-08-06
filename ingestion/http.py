"""One HTTP helper for every source, because they all fail the same ways.

The public APIs this project reads are free and occasionally flaky. Measuring
SIDRA once, from a working connection, it dropped mid-response:

    ChunkedEncodingError: IncompleteRead(621971 bytes read, 711168 more expected)

Without a retry, a blip like that 25 minutes into a scheduled run throws away
everything already fetched. With one, it costs five seconds.

Retries cover transient failures only -- timeouts, dropped connections, 5xx and
429. A 4xx is a bug in the request and repeating it just wastes time: that is
how the IBGE mesh endpoint failure was diagnosed the first time around, and
retrying would have buried it.
"""

from __future__ import annotations

import time

import requests

# Four attempts, waiting 5 s, 10 s then 15 s. Generous because the cost of
# giving up is a ten-minute run thrown away, and the cost of waiting is seconds.
RETRIES = 3
BACKOFF_SECONDS = 5

# Connect and read budgets are separated on purpose. A scheduled run died after
# spending 139 s on a TCP handshake to SIDRA that was never going to complete --
# the per-source timeout is sized for a slow *response*, which is a different
# thing entirely. A connection that has not opened in 10 s is not opening, and
# failing fast there is what lets the retry actually happen.
CONNECT_TIMEOUT = 10

TRANSIENT_ERRORS = (
    requests.Timeout,
    requests.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
)


def _is_transient_http_error(error: requests.HTTPError) -> bool:
    response = error.response
    if response is None:
        return True
    return response.status_code >= 500 or response.status_code == 429


def fetch(
    url: str,
    *,
    params: dict | None = None,
    timeout: int,
    retries: int = RETRIES,
    label: str = "",
) -> requests.Response:
    """GET with a bounded retry. Returns a response whose body is fully read."""
    tag = f"[http] {label or url}"

    budget = (min(CONNECT_TIMEOUT, timeout), timeout)

    for attempt in range(1, retries + 2):
        try:
            response = requests.get(url, params=params, timeout=budget)
            response.raise_for_status()
            # Touch the body here: a truncated response raises on read, not on
            # the call, and the point is to catch that inside the retry.
            _ = response.content
            return response
        except TRANSIENT_ERRORS as error:
            failure = error
        except requests.HTTPError as error:
            if not _is_transient_http_error(error):
                raise
            failure = error

        if attempt > retries:
            raise failure

        wait = BACKOFF_SECONDS * attempt
        print(f"{tag}: attempt {attempt} failed ({type(failure).__name__}); "
              f"retrying in {wait}s", flush=True)
        time.sleep(wait)

    raise AssertionError("unreachable")
