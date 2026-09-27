from checkerduck.db.db import init_database
from checkerduck.extract.extractor import DataExtractor
from checkerduck.db import dao
from model.models import TargetQueryableDomain
from rules.seo_rule import DomainCategoryRule, EvalContext


def main():
    init_database()
    id = "74354b17-c323-4e25-8e2d-13fa99428b9f"
    analysis = dao.get_analysis(id)
    extractor = DataExtractor()
    extractor.run_extract(analysis)

    domains = [TargetQueryableDomain(domain=d.domain) for d in analysis.domains]
    # domains = [TargetQueryableDomain(domain="bitbucket.org")]
    # categories = extractor.cloud_flare_client.query_domain_categories(domains)
    # extractor.store.persist_domain_categories_cloudflare(id, categories)


    rule = DomainCategoryRule("Technology")
    # rule.test()
    # print(rule.domain_similarity(["Technology/Technology"], ["Internet Communication"]))
    # print(rule.domain_similarity(["Technology/Technology"], ["Sports/Sports"]))
    for d in domains:
        print(f"Domain {d.domain}, score: {rule.eval(eval_context=EvalContext(id, d.domain)).score}")

    # print(f"{eval_results}")
    # for d in ["bitchipdigital.com"]:
    #     print(HistoricalOrganicTrafficRule().eval(EvalContext(id, d)))


if __name__ == "__main__":
    main()
    # get_domain_lang("www.ahrefs.com")
    # get_domain_lang("www.dzen.ru")
    # get_domain_lang("dimokratiki.gr")
