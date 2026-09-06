from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Sequence

import requests
from bs4 import BeautifulSoup
import logging

from lingua import LanguageDetectorBuilder
from checkerduck.extract.ahrefs_models import AnalysedDomain
from checkerduck.resources.langs import get_lang_by_country

logger = logging.Logger(__name__)

detector = LanguageDetectorBuilder.from_all_languages().build()

def get_domain_lang_by_top_traffic(top_country_by_traffic: List[tuple[str, int]]) -> str:
    return get_lang_by_country(
        max(top_country_by_traffic, key=lambda x: int(x[1]))[0]
    )


def get_domain_lang(domain: str, lang_by_traffic: str) -> str:
    print(f"Get domain lang for {domain}")
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
            response = requests.get(f"https://{domain}", headers=headers, verify=False)
        except Exception as e:
            logger.warning(f"Failed to get {domain}: {e}, trying http://{domain}")
            response = requests.get(f"http://{domain}", headers=headers, verify=False)

        soup = BeautifulSoup(response.text, "html.parser")
        html_desc = soup.find("meta", attrs={"name": "description"})
        html_desc = html_desc["content"] if html_desc else None
        if html_desc:
            lang = detector.detect_language_of(html_desc).iso_code_639_1.name.lower()
    except Exception as e:
        logger.info(f"No language found for {domain}, fallback to using top 1 country by traffic")
    lang = lang if lang is not None else lang_by_traffic
    print(f"Domain: {domain}, lang: {lang}")
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
                print(f"Failed to get lang for {domain}: {e}")
    return lang_by_domain

def build_lang_by_domain(batch_analysis_results):
    lang_by_domain = {}
    with ThreadPoolExecutor(max_workers=50) as executor:
        future_to_domain = {tgt["domain"]:
                                executor.submit(get_domain_lang, tgt['domain'],
                                                get_domain_lang_by_top_traffic(tgt['org_traffic_top_by_country']))
                            for tgt in batch_analysis_results['targets']}
        for domain, future in future_to_domain.items():
            try:
                lang_by_domain[domain] = future.result()
            except Exception as e:
                # handle or log failure gracefully
                print(f"Failed to get lang for {domain}: {e}")
    return lang_by_domain
