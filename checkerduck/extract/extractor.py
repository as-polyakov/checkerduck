from __future__ import annotations

import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Mapping, Sequence, Callable

from checkerduck.extract.ahrefs_client_typed import AhrefsClient as TypedAhrefsClient
from checkerduck.extract.ahrefs_models import Outcome, Fetched
from checkerduck.db.db import get_thread_connection
from checkerduck.resources.disallowed_words import get_category_forbidden_words_by_lang
from checkerduck.extract.similar_web import SimilarWebClient
from checkerduck.extract.lang import build_lang_by_typed_domain
from checkerduck.model import Analysis
from checkerduck.model.models import TargetQueryableDomain, HasWord, ClassifiedBacklink, ClassifiedAnchor, ClassifiedKeyword
from checkerduck.db.store import Store

BATCH_ANALYSIS_CHUNK = 100
PROGRESS_INTERVAL_S = 2.0
DATE_FROM = "2022-01-01"


def _chunks(seq: Sequence, n: int):
    for i in range(0, len(seq), n):
        yield seq[i: i + n]


class DataExtractor:
    def __init__(self, parallelization_level: int = 50) -> None:
        self.ahrefs_client = TypedAhrefsClient(api_token=os.environ["AHREFS_API_TOKEN"])
        self.similar_web_client = SimilarWebClient(api_token=os.environ.get("SIMILAR_WEB_KEY"))
        self.parallelization_level = parallelization_level
        self.store = Store(get_thread_connection)

    def run_extract(self, analysis: Analysis) -> None:
        target_id = analysis.target_id

        domains = [TargetQueryableDomain(domain=d.domain) for d in analysis.domains]
        if not domains:
            print(f"{target_id}: no domains, nothing to do")
            return

        try:
            print(f"{target_id}: batch analysis for {len(domains)} domains...")
            analysed = []
            for chunk in _chunks(domains, BATCH_ANALYSIS_CHUNK):
                analysed.extend(self.ahrefs_client.batch_analysis(chunk))

            lang_by_domain = build_lang_by_typed_domain(analysed)

            self.store.persist_batch_analysis(target_id, analysed, lang_by_domain)
            print(f"{target_id}: saved {len(analysed)} batch-analysis rows")

            update_targets_with_lang(domains, lang_by_domain)
            words_by_cat_by_lang = get_category_forbidden_words_by_lang(domains)

            # self.process_single_domain(analysis.target_id, domains[0], words_by_cat_by_lang)
            results, failures = self.process_all_domains(target_id, domains, words_by_cat_by_lang)
            print(f"{target_id}: extracted, ok={len(results)} failed={len(failures)}")

            # sim_web_report_id = self.similar_web_client.submit_request_report(
            #     [d.domain for d in domains])["report_id"]
            # categories = self.similar_web_client.download_report_as_domain_categories(
            #     sim_web_report_id)
            # store.persist_domain_categories(target_id, categories)

        except Exception:
            print(traceback.format_exc())
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
                    print(traceback.format_exc())
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
        targets = [domain]

        # Fetch first, persist after. Never hold a write open across a network
        # call — that is the one way this threading model goes wrong.
        print(f"{domain.domain}: querying...")
        metrics = client.query_metric_history(targets, DATE_FROM)
        pages = client.query_top_pages(targets, query_date)
        incoming_anchors = client.query_incoming_anchors(targets, words_by_category_by_lang)
        outgoing_anchors = client.query_outgoing_anchors(targets, words_by_category_by_lang)
        organic_keywords = client.query_organic_keywords(targets, query_date, words_by_category_by_lang)

        incoming = self._label_all(incoming_anchors, ClassifiedBacklink.of, words_by_category_by_lang)
        outgoing = self._label_all(outgoing_anchors, ClassifiedAnchor.of, words_by_category_by_lang)
        keywords = self._label_all(organic_keywords, ClassifiedKeyword.of, words_by_category_by_lang)

        self.store.persist_metrics_history(target_id, metrics)
        self.store.persist_top_pages(target_id, pages, query_date)

        self.store.persist_incoming_anchors(target_id, incoming)
        self.store.persist_outgoing_anchors(target_id, outgoing)
        self.store.persist_organic_keywords(target_id, keywords, query_date)
        print(f"{domain.domain}: done")

    def _label_all[D: HasWord, C](self, outcomes: Mapping[TargetQueryableDomain, Outcome[D]],
                                  into: Callable[[D, str | None], C],
                                  words_by_category_by_lang: Mapping[str, Mapping[str, str]]) -> dict[
        TargetQueryableDomain, Outcome[C]]:
        out: dict[TargetQueryableDomain, Outcome[C]] = {}
        for queryyableDomain, outcome in outcomes.items():
            match outcome:
                case Fetched(rows=rows, truncated=truncated):
                    categories = words_by_category_by_lang.get(queryyableDomain.lang or "", {})
                    out[queryyableDomain] = Fetched(
                        domain=queryyableDomain.domain,
                        rows=[into(r, self._category(categories, r.get_word()))
                              for r in rows],
                        truncated=truncated,
                    )
                case _:
                    out[queryyableDomain] = outcome
        return out

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


