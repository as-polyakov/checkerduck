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
from checkerduck.db.store import Store
from checkerduck.resources.disallowed_words import get_category_forbidden_words_by_lang
from checkerduck.extract.similar_web import SimilarWebClient
from checkerduck.extract.lang import build_lang_by_typed_domain
from checkerduck.model import Analysis
from checkerduck.model.models import TargetQueryableDomain, HasWord, ClassifiedBacklink, ClassifiedAnchor, \
    ClassifiedKeyword
from checkerduck.extract.cloud_flare_client_typed import TypedCloudFlareClient

log = logging.getLogger(__name__)

PROGRESS_INTERVAL_S = 2.0
DATE_FROM = "2026-01-01"


class DataExtractor:
    def __init__(self, analysis: Analysis, parallelization_level: int = 50) -> None:
        self.ahrefs_client = TypedAhrefsClient(api_token=os.environ["AHREFS_API_TOKEN"])
        self.cloud_flare_client = TypedCloudFlareClient(api_token=os.environ["CF_TOKEN"],
                                                        account_id=os.environ["CF_ACCOUNT_ID"])
        self.similar_web_client = SimilarWebClient(api_token=os.environ["SIMILAR_WEB_KEY"])
        self.parallelization_level = parallelization_level
        self.store = Store(get_thread_connection)
        self.analysis = analysis
        self.fetched_at = analysis.created_at

    def run_extract(self) -> None:
        analysis = self.analysis
        target_id = analysis.target_id

        domains = [TargetQueryableDomain(domain=d.domain) for d in analysis.domains]
        if not domains:
            log.info("%s: no domains, nothing to do", target_id)
            return

        try:
            stale_categories_domains = [
                d for d in domains if not self.store.is_domain_categories_fresh(d.domain)
            ]
            log.info(
                "%s: categories fresh=%d queried=%d",
                target_id, len(domains) - len(stale_categories_domains), len(stale_categories_domains),
            )
            if stale_categories_domains:
                categories = self.cloud_flare_client.query_domain_categories(stale_categories_domains)
                self.store.persist_domain_categories_cloudflare(self.fetched_at, categories)
                log.info("%s: saved %d categories for %d domains", target_id, len(categories),
                         len(stale_categories_domains),
                         )

            stale_batch_domains = [d for d in domains if not self.store.is_batch_analysis_fresh(d.domain)]
            log.info(
                "%s: batch analysis fresh=%d queried=%d",
                target_id, len(domains) - len(stale_batch_domains), len(stale_batch_domains),
            )
            analysed = self.ahrefs_client.batch_analysis(stale_batch_domains) if stale_batch_domains else []
            new_langs_by_domain = build_lang_by_typed_domain(analysed) if analysed else {}
            if analysed:
                self.store.persist_batch_analysis(self.fetched_at, analysed, new_langs_by_domain)
                log.info("%s: persisted %d batch-analysis rows", target_id, len(analysed))

            self.enrich_targets_with_lang(domains)
            words_by_cat_by_lang = get_category_forbidden_words_by_lang(domains)

            results, failures = self.process_all_domains(target_id, domains, words_by_cat_by_lang)
            log.info("%s: extracted, ok=%d failed=%d", target_id, len(results), len(failures))

            # sim_web_report_id = self.similar_web_client.submit_request_report(
            #     [d.domain for d in domains])["report_id"]
            # categories = self.similar_web_client.download_report_as_domain_categories(
            #     sim_web_report_id)
            # self.store.persist_domain_categories(categories)

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
                pool.submit(self.process_single_domain, d, words_by_category_by_lang): d
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
            domain: TargetQueryableDomain,
            words_by_category_by_lang: Mapping[str, Mapping[str, str]],
    ) -> None:
        client = self.ahrefs_client
        query_date = date.today().strftime("%Y-%m-%d")
        d = domain.domain
        words = words_by_category_by_lang

        log.debug("%s: querying", d)
        self._fetch_if_stale(
            d, "metrics history",
            self.store.is_metrics_history_fresh(d),
            lambda: client.query_metric_history(domain, DATE_FROM),
            lambda result, fetched_at: self.store.persist_metrics_history(fetched_at, result),
        )
        self._fetch_if_stale(
            d, "top pages",
            self.store.is_top_pages_fresh(d),
            lambda: client.query_top_pages(domain, query_date),
            lambda result, fetched_at: self.store.persist_top_pages(fetched_at, result, query_date),
        )
        self._fetch_if_stale(
            d, "backlinks",
            self.store.is_backlinks_fresh(d),
            lambda: self._label_all(domain, client.query_backlinks(domain), ClassifiedBacklink.of, words),
            lambda result, fetched_at: self.store.persist_backlinks(fetched_at, result),
        )
        self._fetch_if_stale(
            d, "outgoing anchors",
            self.store.is_outgoing_anchors_fresh(d),
            lambda: self._label_all(
                domain, client.query_outgoing_anchors(domain, words), ClassifiedAnchor.of, words,
            ),
            lambda result, fetched_at: self.store.persist_outgoing_anchors(fetched_at, result),
        )
        self._fetch_if_stale(
            d, "organic keywords",
            self.store.is_organic_keywords_fresh(d),
            lambda: self._label_all(
                domain, client.query_organic_keywords(domain, query_date, words), ClassifiedKeyword.of, words,
            ),
            lambda result, fetched_at: self.store.persist_organic_keywords(
                fetched_at, result, query_date,
            ),
        )
        log.debug("%s: done", d)

    def _fetch_if_stale(self, domain: str, data_name: str, fresh: bool, fetch, persist) -> None:
        if fresh:
            log.info("%s: skipping fresh %s", domain, data_name)
            return
        log.info("%s: querying and persisting %s", domain, data_name)
        persist(fetch(), self.fetched_at)

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

    def enrich_targets_with_lang(self, targets: Sequence[TargetQueryableDomain]) -> None:
        for target in targets:
            target.lang = self.store.detected_lang(target.domain)
