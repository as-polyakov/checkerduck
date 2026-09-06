from checkerduck.db.db import init_database
from checkerduck.extract.extractor import DataExtractor
from checkerduck.db import dao


def main():
    init_database()
    id = "74354b17-c323-4e25-8e2d-13fa99428b9f"
    analysis = dao.get_analysis(id)
    extractor = DataExtractor()
    extractor.run_extract(analysis)


    # eval_results = [evaluate_domain(id, domain.domain)
    #                 for domain in analysis.domains]

    # print(f"{eval_results}")
    # for d in ["bitchipdigital.com"]:
    #     print(HistoricalOrganicTrafficRule().eval(EvalContext(id, d)))


if __name__ == "__main__":
    main()
    # get_domain_lang("www.ahrefs.com")
    # get_domain_lang("www.dzen.ru")
    # get_domain_lang("dimokratiki.gr")
