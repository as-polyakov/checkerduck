import logging

import pandas as pd

from checkerduck import log as logsetup
from checkerduck.db.db import init_database
from checkerduck.db.store import fetched_at_now
from checkerduck.extract.extractor import DataExtractor
from checkerduck.model.models import Analysis, AnalysisDomain
from checkerduck.rules.rule_aggregator import evaluate_domain

log = logging.getLogger("checkerduck.main")


def main():

    logsetup.setup()
    init_database(db_path="checkerduck.db")
    candidate_domains = pd.read_csv('candidate_domains.csv')

    analysis = Analysis(
        target_id="x",
        name=None,
        status=None,
        created_at=fetched_at_now(),
        completed_at=None,
        processed_domains=None,
        domains=[
            # AnalysisDomain(domain=d, price_usd=0, notes=None) for d in candidate_domains['url'][:200]],
            AnalysisDomain(domain=d, price_usd=0, notes=None) for d in [
               'appsgeyser.io',
               'on-magazine.co.uk',
               'bestutahrealestate.com',
               'englishvers.com',
               'itsupplychain.com',
               'designyourway.net',
               'pc-bottleneck.com',
               'dearblessings.com',
               'newsgram.com',
               'finchannel.com'
            ]],
    )
    log.info("Analysis created with date %s", analysis.created_at)
    extractor = DataExtractor(analysis)
    extractor.run_extract()
    eval_results = [evaluate_domain(analysis.target_id, domain.domain)
                    for domain in analysis.domains]
    print(eval_results)
    # id = "74354b17-c323-4e25-8e2d-13fa99428b9f"
    # analysis = Analysis(
    #     target_id="x",
    #     name=None,
    #     status=None,
    #     created_at=None,
    #     completed_at=None,
    #     processed_domains=None,
    #     domains=[
    #         AnalysisDomain(domain=d, price_usd=0, notes=None) for d in candidate_domains['url'][:200]],
    # )

    # categories = extractor.cloud_flare_client.query_domain_categories([
    #
    #     TargetQueryableDomain(domain="amourvert.com"),
    #     TargetQueryableDomain(domain="arabamerica.com"),
    #
    # ])

    # One adapter for both schemes: they then share a single pool.
    # domains = [TargetQueryableDomain(domain=d.domain) for d in analysis.domains]
    # domains = [TargetQueryableDomain(domain="bitbucket.org")]
    # categories = extractor.cloud_flare_client.query_domain_categories(domains)
    # extractor.store.persist_domain_categories_cloudflare(fetched_at_now(), categories)

    # rule = DomainCategoryRule("Technology")
    # rule.test()
    # print(rule.domain_similarity(["Technology/Technology"], ["Internet Communication"]))
    # print(rule.domain_similarity(["Technology/Technology"], ["Sports/Sports"]))
    # for d in domains:
    #     log.info("%s: score=%s", d.domain, rule.eval(eval_context=EvalContext(id, d.domain)).score)

    # print(f"{eval_results}")
    # for d in ["bitchipdigital.com"]:
    #     print(HistoricalOrganicTrafficRule().eval(EvalContext(id, d)))


if __name__ == "__main__":
    main()
    # get_domain_lang("www.ahrefs.com")
    # get_domain_lang("www.dzen.ru")
    # get_domain_lang("dimokratiki.gr")
