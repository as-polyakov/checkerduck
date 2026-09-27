from __future__ import annotations

from typing import Mapping

import requests
from requests.adapters import HTTPAdapter, Retry

RETRYABLE_STATUS = (429, 500, 502, 503, 504)
DEFAULT_POOL_SIZE = 64


def new_session(
        *,
        headers: Mapping[str, str] | None = None,
        total_retries: int = 4,
        backoff_factor: float = 1.0,
        pool_size: int = DEFAULT_POOL_SIZE,
) -> requests.Session:
    session = requests.Session()
    if headers:
        session.headers.update(headers)

    retry = Retry(
        total=total_retries,
        status_forcelist=RETRYABLE_STATUS,
        allowed_methods=frozenset({"GET", "POST"}),
        backoff_factor=backoff_factor,
        backoff_jitter=1.0,
        backoff_max=30.0,
        respect_retry_after_header=True,
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=pool_size,
        pool_maxsize=pool_size,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
