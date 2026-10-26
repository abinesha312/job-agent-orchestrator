"""HTTP with a couple retries. 404s fail fast, 503s get another shot."""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from job_agent.errors import HttpFailure

_RETRY_STATUS = {429, 500, 502, 503, 504}
_UA = "applypilot/0.1 (personal job search)"


def request(
    method: str,
    url: str,
    *,
    client: httpx.Client | None = None,
    params: dict | None = None,
    timeout: float = 15.0,
    retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    headers: dict | None = None,
) -> httpx.Response:
    owns = client is None
    client = client or httpx.Client(timeout=timeout, headers={"user-agent": _UA})
    delay = 0.25
    last: Exception | None = None
    try:
        for attempt in range(1, max(retries, 1) + 1):
            try:
                resp = client.request(method, url, params=params, timeout=timeout, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = exc
                if attempt >= retries:
                    raise HttpFailure(f"network error for {url}: {exc}", url=url) from exc
                sleep(delay)
                delay *= 2
                continue
            if resp.status_code in _RETRY_STATUS:
                last = HttpFailure(
                    f"{resp.status_code} from {url}", url=url, status=resp.status_code, retryable=True,
                )
                if attempt >= retries:
                    raise last
                sleep(delay)
                delay *= 2
                continue
            if resp.status_code >= 400:
                raise HttpFailure(
                    f"{resp.status_code} from {url}", url=url, status=resp.status_code, retryable=False,
                )
            return resp
    finally:
        if owns:
            client.close()
    raise HttpFailure(f"gave up on {url}: {last}", url=url)
