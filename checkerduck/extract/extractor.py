from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Mapping, Sequence, Callable

from checkerduck.extract.ahrefs_client_typed import AhrefsClient as TypedAhrefsClient
from checkerduck.extract.client_typed import Outcome, Fetched
from checkerduck.db.db import get_thread_connection
from checkerduck.resources.disallowed_words import get_category_forbidden_words_by_lang
from checkerduck.extract.similar_web import SimilarWebClient
from checkerduck.extract.lang import build_lang_by_typed_domain
from checkerduck.model import Analysis
from checkerduck.model.models import TargetQueryableDomain, HasWord, ClassifiedBacklink, ClassifiedAnchor, \
    ClassifiedKeyword
from checkerduck.db.store import Store
from checkerduck.extract.cloud_flare_client_typed import TypedCloudFlareClient

log = logging.getLogger(__name__)

PROGRESS_INTERVAL_S = 2.0
DATE_FROM = "2026-01-01"


class DataExtractor:
    def __init__(self, parallelization_level: int = 50) -> None:
        self.ahrefs_client = TypedAhrefsClient(api_token=os.environ["AHREFS_API_TOKEN"])
        self.cloud_flare_client = TypedCloudFlareClient(api_token=os.environ["CF_TOKEN"],
                                                        account_id=os.environ["CF_ACCOUNT_ID"])
        self.similar_web_client = SimilarWebClient(api_token=os.environ.get("SIMILAR_WEB_KEY"))
        self.parallelization_level = parallelization_level
        self.store = Store(get_thread_connection)

    def run_extract(self, analysis: Analysis) -> None:
        target_id = analysis.target_id

        domains = [TargetQueryableDomain(domain=d.domain) for d in analysis.domains]
        if not domains:
            log.info("%s: no domains, nothing to do", target_id)
            return

        try:
            log.info("%s: querying categories %d domains", target_id, len(domains))
            categories = self.cloud_flare_client.query_domain_categories(domains)
            self.store.persist_domain_categories_cloudflare(target_id, categories)
            log.info("%s: saved %d categories for %d domains", target_id, len(categories), len(domains))

            log.info("%s: batch analysis for %d domains", target_id, len(domains))
            analysed = self.ahrefs_client.batch_analysis(domains)
            lang_by_domain = build_lang_by_typed_domain(analysed)

            self.store.persist_batch_analysis(target_id, analysed, lang_by_domain)
            log.info("%s: saved %d batch-analysis rows", target_id, len(analysed))

            update_targets_with_lang(domains, lang_by_domain)
            words_by_cat_by_lang = get_category_forbidden_words_by_lang(domains)

            # self.process_single_domain(analysis.target_id, domains[0], words_by_cat_by_lang)
            results, failures = self.process_all_domains(target_id, domains, words_by_cat_by_lang)
            log.info("%s: extracted, ok=%d failed=%d", target_id, len(results), len(failures))

            # sim_web_report_id = self.similar_web_client.submit_request_report(
            #     [d.domain for d in domains])["report_id"]
            # categories = self.similar_web_client.download_report_as_domain_categories(
            #     sim_web_report_id)
            # store.persist_domain_categories(target_id, categories)

        except Exception:
            log.exception("%s: extract failed", target_id)
            raise

    # ------------------------------------------------------- fan out

    def process_all_domains(
            self,
            target_id: str,
            domains: Sequence[TargetQueryableDomain],
            words_by_category_by_lang: Mapping[str, Mapping[str, str]],
    ):
        results, failures = [], []
        done = 0
        last_flush = 0.0

        with ThreadPoolExecutor(max_workers=self.parallelization_level) as pool:
            futures = {
                pool.submit(self.process_single_domain, target_id, d, words_by_category_by_lang): d
                for d in domains
            }
            for future in as_completed(futures):
                domain = futures[future]
                try:
                    results.append((domain, future.result()))
                except Exception as e:
                    log.exception("%s: failed", domain.domain)
                    failures.append((domain, e))
                finally:
                    done += 1
                    now = time.monotonic()
                    if now - last_flush >= PROGRESS_INTERVAL_S or done == len(domains):
                        self.store.set_processed(target_id, done)
                        last_flush = now

        return results, failures

    # ---------------------------------------------------- one domain

    def process_single_domain(
            self,
            target_id: str,
            domain: TargetQueryableDomain,
            words_by_category_by_lang: Mapping[str, Mapping[str, str]],
    ) -> None:
        client = self.ahrefs_client
        query_date = date.today().strftime("%Y-%m-%d")

        log.debug("%s: querying", domain.domain)
        metrics = client.query_metric_history(domain, DATE_FROM)
        pages = client.query_top_pages(domain, query_date)
        raw_backlinks = client.query_backlinks(domain)
        outgoing_anchors = client.query_outgoing_anchors(domain, words_by_category_by_lang)
        organic_keywords = client.query_organic_keywords(domain, query_date, words_by_category_by_lang)

        classified_backlinks = self._label_all(domain, raw_backlinks, ClassifiedBacklink.of, words_by_category_by_lang)
        classified_anchors = self._label_all(domain, outgoing_anchors, ClassifiedAnchor.of, words_by_category_by_lang)
        classified_keywords = self._label_all(domain, organic_keywords, ClassifiedKeyword.of, words_by_category_by_lang)

        log.debug("%s: persisting", domain.domain)
        self.store.persist_metrics_history(target_id, metrics)
        self.store.persist_top_pages(target_id, pages, query_date)
        self.store.persist_backlinks(target_id, classified_backlinks)
        self.store.persist_outgoing_anchors(target_id, classified_anchors)
        self.store.persist_organic_keywords(target_id, classified_keywords, query_date)
        log.debug("%s: done", domain.domain)

    def _label_all[D: HasWord, C](self, domain: TargetQueryableDomain, outcome: Outcome[D],
                                  into: Callable[[D, str | None], C],
                                  words_by_category_by_lang: Mapping[str, Mapping[str, str]]) -> Outcome[C]:
        match outcome:
            case Fetched(rows=rows, truncated=truncated):
                categories = words_by_category_by_lang.get(domain.lang or "", {})
                return Fetched(
                    domain=domain.domain,
                    rows=[into(r, self._category(categories, r.get_word()))
                          for r in rows],
                    truncated=truncated,
                )
            case _:
                return outcome

    @staticmethod
    def _category(words_by_categories: Mapping[str, str], text: str | None) -> str | None:
        if not text:
            return None
        lowered = text.lower()
        for word in sorted(words_by_categories, key=len, reverse=True):
            if word.lower() in lowered:
                return words_by_categories[word]
        return None


def update_targets_with_lang(
        targets: Sequence[TargetQueryableDomain], lang_by_domain: Mapping[str, str]
) -> None:
    for target in targets:
        # .get, not [] — a domain missing from batch analysis used to raise
        # KeyError here and kill the whole run.
        target.lang = lang_by_domain.get(target.domain)
