import logging
from dataclasses import replace, dataclass
from typing import Any, Callable, Collection, Self, Mapping, Sequence

import msgspec
import requests

from checkerduck.extract.http import new_session
from checkerduck.log import HTTP_LOGGER
from checkerduck.model.models import TargetQueryableDomain

log = logging.getLogger(HTTP_LOGGER)

# How much of a raw body to log. CHECKERDUCK_HTTP_DEBUG=1 turns the debug line on.
BODY_CHARS = 2000


def construct_field_or(field: str, conditions: Collection) -> dict:
    # conditions = conditions[:1]
    if len(conditions) == 0:
        return {}
    return {"or": [
        {"field": field,
         "modifier": "lowercase",
         "is": ["phrase_match", cond]} for cond in conditions]}


@dataclass(frozen=True)
class Endpoint[E, R]:
    path: str
    row: type[R]
    extract_data_per_row: Callable[[E], Mapping[str, list[R]]]
    decoder: msgspec.json.Decoder[E]

    def with_path_params(self, path_params: list[str]) -> Self:
        return replace(self, path="/".join([self.path.rstrip("/"), *path_params]))


@dataclass(frozen=True)
class Fetched[R]:
    domain: str
    rows: list[R]
    truncated: bool = False


@dataclass(frozen=True)
class NoData:
    domain: str


@dataclass(frozen=True)
class Failed:
    domain: str
    error: str
    status: int | None = None


type Outcome[R] = Fetched[R] | NoData | Failed


def new_endpoint[E, R](path: str, response_object: type[E], row: type[R],
                       extract_per_row: Callable[[E], Mapping[str, list[R]]]) -> Endpoint[E, R]:
    return Endpoint(path, row, extract_per_row, msgspec.json.Decoder(response_object))


class TypedHTTPJSONClient:

    def __init__(self, base_url: str, api_token: str, timeout: int = 90):
        self.base_url = base_url
        self.timeout = timeout
        # Retry/backoff/pooling policy lives in extract.http, not here.
        self.session = new_session(
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            }
        )

    def _request(self, method: str, endpoint: str, **kwargs) -> bytes:
        r = self.session.request(method, f"{self.base_url}{endpoint}",
                                 timeout=self.timeout, **kwargs)
        if not r.ok:
            log.warning("%s %s -> %s %s", method, r.url, r.status_code, r.text[:BODY_CHARS])
        elif log.isEnabledFor(logging.DEBUG):
            # r.text is not free on a 100KB backlinks page; only build it in debug.
            log.debug("%s %s -> %s %s", method, r.url, r.status_code, r.text[:BODY_CHARS])
        r.raise_for_status()
        return r.content

    def _get_bytes(self, endpoint: str, params: dict[str, Any]) -> bytes:
        return self._request("GET", endpoint, params=params)

    def _post_bytes(self, endpoint: str, payload: dict[str, Any]) -> bytes:
        return self._request("POST", endpoint, json=payload)

    def _fetch_bulk_domain_rows[E, R](self, domains: Sequence[TargetQueryableDomain], endpoint: Endpoint[E, R],
                                      params: dict) -> Mapping[TargetQueryableDomain, Outcome[R]]:

        def for_each_domain(outcome_factory: Callable[[str], Outcome[R]]) -> Mapping[TargetQueryableDomain, Outcome[R]]:
            return {t: outcome_factory(t.domain) for t in domains}

        try:
            raw = self._get_bytes(endpoint.path, params)
        except requests.RequestException as e:
            status = (e.response.status_code if isinstance(e, requests.HTTPError) and e.response is not None else None)
            return for_each_domain(lambda d: Failed(domain=d, error=str(e), status=status))
        try:
            rows = endpoint.extract_data_per_row(endpoint.decoder.decode(raw))
        except msgspec.DecodeError as e:
            return for_each_domain(lambda d: Failed(domain=d, error=f"malformed body: {e}"))

        if not rows:
            return for_each_domain(lambda d: NoData(domain=d))

        def to_outcome(domain: str, all_rows: Mapping[str, list[R]]) -> Outcome[R]:
            if not all_rows[domain]:
                return NoData(domain=domain)
            else:
                return Fetched(domain=domain, rows=all_rows[domain], truncated=False)

        return for_each_domain(lambda d: to_outcome(domain=d, all_rows=rows))

    def _fetch_per_domain_rows[E, R](self, domain: TargetQueryableDomain, endpoint: Endpoint[E, R],
                                     params: dict) -> Outcome[R]:
        res = self._fetch_bulk_domain_rows(domains=[domain], endpoint=endpoint, params=params)
        return res[domain]
