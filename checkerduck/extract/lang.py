from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Sequence

from bs4 import BeautifulSoup
import logging

from lingua import LanguageDetectorBuilder
from checkerduck.extract.ahrefs_models import AnalysedDomain
from checkerduck.extract.http import new_session
from checkerduck.resources.langs import get_lang_by_country

log = logging.getLogger(__name__)

# These are arbitrary third-party sites, not an API: dead and parked domains are
# expected, and lang_by_traffic is a perfectly good fallback. So one cheap retry
# rather than the API policy — 50 unreachable domains must not cost 50 x 14s.
# The session also buys connection reuse, which bare requests.get did not.
_session = new_session(total_retries=1, backoff_factor=0.5)

# (connect, read). Unbounded waits here pin a worker in the 50-thread pool.
HOMEPAGE_TIMEOUT = (5, 5)

detector = LanguageDetectorBuilder.from_all_languages().build()

def get_domain_lang_by_top_traffic(top_country_by_traffic: List[tuple[str, int]]) -> str:
    return get_lang_by_country(
        max(top_country_by_traffic, key=lambda x: int(x[1]))[0]
    )


def get_domain_lang(domain: str, lang_by_traffic: str) -> str:
    log.debug("%s: detecting lang", domain)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/117.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    lang = None
    try:
        try:
            response = _session.get(f"https://{domain}", headers=headers, verify=False,
                                    timeout=HOMEPAGE_TIMEOUT)
        except Exception as e:
            log.debug("%s: https failed (%s), trying http", domain, e)
            response = _session.get(f"http://{domain}", headers=headers, verify=False,
                                    timeout=HOMEPAGE_TIMEOUT)

        soup = BeautifulSoup(response.text, "html.parser")
        html_desc = soup.find("meta", attrs={"name": "description"})
        html_desc = html_desc["content"] if html_desc else None
        if html_desc:
            lang = detector.detect_language_of(html_desc).iso_code_639_1.name.lower()
    except Exception as e:
        log.debug("%s: no lang in page, falling back to top-traffic country", domain)
    lang = lang if lang is not None else lang_by_traffic
    log.debug("%s: lang=%s", domain, lang)
    return lang


def build_lang_by_typed_domain(analyzed_domains: Sequence[AnalysedDomain]):
    lang_by_domain = {}
    with ThreadPoolExecutor(max_workers=50) as executor:
        future_to_domain = {tgt.domain:
                                executor.submit(get_domain_lang, tgt.domain,
                                                get_domain_lang_by_top_traffic(tgt.metrics.org_traffic_top_by_country))
                            for tgt in analyzed_domains}
        for domain, future in future_to_domain.items():
            try:
                lang_by_domain[domain] = future.result()
            except Exception as e:
                # handle or log failure gracefully
                log.warning("%s: lang detection failed: %s", domain, e)
    return lang_by_domain