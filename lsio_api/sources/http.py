import time
from typing import Any

import httpx2

USER_AGENT = "linuxserver-static-api (+https://github.com/linuxserver/static-api)"


def client() -> httpx2.Client:
    return httpx2.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=60)


def request_json(
    http: httpx2.Client,
    method: str,
    url: str,
    *,
    retries: int = 3,
    backoff: float = 1.5,
    max_wait: float = 60,
    **kwargs: Any,
) -> Any:
    """
    JSON from `url`, retrying network errors, 429 and 5xx with exponential backoff (or the server's
    Retry-After, up to `max_wait` seconds). Raises on any other error.
    """
    for attempt in range(retries + 1):
        wait = backoff * 2**attempt
        try:
            res = http.request(method, url, **kwargs)
        except httpx2.TransportError:
            if attempt == retries:
                raise
        else:
            if res.is_success:
                return res.json()
            if attempt == retries or (res.status_code != 429 and res.status_code < 500):
                res.raise_for_status()
            retry_after = res.headers.get("retry-after", "")
            if retry_after.isdigit():
                wait = float(retry_after)
        time.sleep(min(wait, max_wait))
    raise AssertionError("unreachable")
