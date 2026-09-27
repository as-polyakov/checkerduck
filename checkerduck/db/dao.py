from datetime import datetime
from typing import Dict, List, Tuple, Sequence

from checkerduck.db.db import get_thread_connection
from checkerduck.db.db import LinkDirection
from checkerduck.model import Analysis, AnalysisStatus
from checkerduck.resources.disallowed_words import ForbiddenWordCategory
from checkerduck.model.models import RuleEvaluation, AnalysisDomain
from checkerduck.domain.utils import safe_int
from checkerduck.resources.cloudflare_categories import CloudFlareCategory


def select_one(query: str, params: tuple = ()) -> dict | None:
    cur = get_thread_connection().cursor()
    cur.execute(query, params)
    row = cur.fetchone()
    return dict(row) if row else None


def select_all(query: str, params: tuple = ()) -> list[dict]:
    cur = get_thread_connection().cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def insert_one(query: str, params: tuple = ()):
    cur = get_thread_connection().cursor()
    cur.execute(query, params)
    get_thread_connection().commit()


def update_analysis_status(analysis_id: str, status: AnalysisStatus) -> None:
    cur = get_thread_connection().cursor()
    cur.execute("update analysis set status = ? where target_id = ?", (status, analysis_id))
    get_thread_connection().commit()


def get_rule_evaluations(analysis_id: str) -> dict[str, List[RuleEvaluation]]:
    cur = get_thread_connection().cursor()
    res: dict[str, List[RuleEvaluation]] = {}
    rows = select_all(
        "select domain, rule, score, critical_violation,details  from rules_evaluation_results where target_id = ?",
        (analysis_id,))
    for row in rows:
        if row["domain"] not in res:
            res[row["domain"]] = []
        res[row["domain"]].append(
            RuleEvaluation(row["domain"], row["rule"], row["score"], row["critical_violation"], row["details"]))
    return res


def persist_rule_evaluations(analysis_id: str, evals: list[list[RuleEvaluation]]) -> None:
    cur = get_thread_connection().cursor()
    for eval_by_domain in evals:
        for eval in eval_by_domain:
            cur.execute(
                "insert into rules_evaluation_results (target_id, domain, rule, score, critical_violation, details) VALUES (?, ?, ?, ?, ?, ?)",
                (analysis_id, eval.domain, eval.rule, eval.score, eval.critical_violation, eval.details))
    get_thread_connection().commit()


# def get_analysis(analysis: Analysis) -> None:
def persist_analysis(analysis: Analysis) -> None:
    insert_one(
        "insert into analysis (target_id, name, status, created_at, completed_at) VALUES (?, ?, ?, ?, ?)",
        (
            analysis.target_id, analysis.name, analysis.status, safe_date_to_str(analysis.created_at),
            safe_date_to_str(analysis.completed_at)))
    for domain in analysis.domains:
        insert_one("insert into analysis_domains (target_id, domain, price_usd, notes) VALUES (?, ?, ?, ?)",
                   (analysis.target_id, domain.domain, domain.price_usd, domain.notes))
    get_thread_connection().commit()


def safe_date_to_str(date: datetime) -> str:
    return date.strftime("%Y-%m-%d %H:%M:%S") if date else None


def safe_date_from_str(datestr: str) -> datetime:
    return datetime.strptime(datestr, "%Y-%m-%d %H:%M:%S") if datestr else None


def get_recent_analysis() -> list[dict]:
    return select_all(
        """
        select target_id,
               name,
               status,
               created_at,
               completed_at,
               (select count(*) from analysis_domains where target_id = analysis.target_id) as "total_domains",
               processed_domains
        from analysis
        order by created_at, completed_at desc
        """, ())


def get_analysis(analysis_id: str) -> Analysis:
    h = select_one(
        """
        select target_id,
               name,
               status,
               created_at,
               completed_at,
               (select count(*) from analysis_domains where target_id = analysis.target_id) as "total_domains",
               processed_domains
        from analysis
        where target_id = ?
        """, (analysis_id,))
    domains = select_all("select domain, price_usd, notes from analysis_domains where target_id = ?", (analysis_id,))
    return Analysis(h["target_id"], h["name"], h["status"], safe_date_from_str(h["created_at"]),
                    safe_date_from_str(h["completed_at"]),
                    [AnalysisDomain(d["domain"], d["price_usd"], d["notes"]) for d in domains],
                    int(h["processed_domains"]))


def store_rule_evaluations(analysis_id: str, res: List[RuleEvaluation]) -> None:
    cur = get_thread_connection().cursor()
    for rule_ev in res:
        cur.execute(
            "insert into rules_evaluation_results (target_id, domain, rule, score, critical_violation, details) VALUES (?, ?, ?, ?, ?, ?)",
            (analysis_id, rule_ev.domain, rule_ev.__class__.__name__, rule_ev.score, rule_ev.critical_violation,
             rule_ev.details))


# def get_backlinks_forbidden_words(target_id: str, domain: str, category: ForbiddenWordCategory) -> list[dict[str, str]]:
#     return select_all(
#         "select keyword, keyword_country, is_best_position_set_top_3,is_best_position_set_top_4_10, is_best_position_set_top_11_50, best_position_url from ahrefs_organic_keywords where " +
#         "target_id = ? and domain = ? and forbidden_word_category = ?",
#         (target_id, domain, category))

def get_organic_keywords_forbidden_words(target_id: str, domain: str, category: ForbiddenWordCategory) -> list[
    dict[str, str]]:
    return select_all(
        "select keyword, keyword_country, is_best_position_set_top_3,is_best_position_set_top_4_10, is_best_position_set_top_11_50, best_position_url from ahrefs_organic_keywords where " +
        "target_id = ? and domain = ? and forbidden_word_category = ?",
        (target_id, domain, category))


def get_backlinks(target_id: str, domain: str) -> list[dict[str, str]]:
    return select_all(
        "select anchor, is_spam from ahrefs_backlinks where " +
        "target_id = ? and domain = ?",
        (target_id, domain))


def get_anchors_forbidden_words(target_id: str, domain: str,
                                direction: LinkDirection, category: ForbiddenWordCategory) -> list[dict[str, str]]:
    return select_all(
        "select anchor, forbidden_word_category, title from anchors_forbidden_words where " +
        "target_id = ? and domain = ? and direction = ? and forbidden_word_category = ?",
        (target_id, domain, direction, category))


def get_domain_top_page_traffic_pcs(target_id: str, domain: str) -> int:
    traffic_by_position = get_top_pages_traffic(target_id, domain)
    top1 = int(traffic_by_position[1][1])
    sum_rest = sum(map(lambda x: int(x[1]), traffic_by_position.values()))
    return int(100 * top1 / sum_rest)


def get_top_pages_traffic(target_id: str, domain: str) -> Dict[int, Tuple[str, int]]:
    return {r["position"]:
                (r["top_keyword_best_position_title"], int(r["sum_traffic"])) for r in select_all(
        "select position, top_keyword_best_position_title, sum_traffic from ahrefs_top_pages where target_id = ? and domain = ?",
        (target_id, domain))}


def get_in_out_num_domains(target_id: str, domain: str) -> (int, int):
    res = select_one(
        "select linked_domains_dofollow, refdomains_dofollow from batch_analysis where target_id = ? and domain = ?",
        (target_id, domain))
    return safe_int(res["linked_domains_dofollow"]), safe_int(res["refdomains_dofollow"])


def get_domain_top_traffic_geographies(target_id: str, domain: str, top_n: int) -> List[str]:
    traffic_by_country = get_domain_traffic_by_country(target_id, domain)
    ranked = sorted(traffic_by_country, key=traffic_by_country.get, reverse=True)
    return ranked[:top_n]


def get_domain_traffic_by_date(target_id: str, domain: str) -> Dict[str, int]:
    organic_traffic_by_date = select_all(
        "select date, org_traffic from ahrefs_metrics_history where target_id = ? and domain = ?",
        (target_id, domain))
    res = {e["date"]: int(e["org_traffic"]) for e in organic_traffic_by_date}
    return res


def get_domain_traffic_by_country(target_id: str, domain: str) -> Dict[str, int]:
    organic_traffic = select_all(
        "select country_code, traffic from ahrefs_org_traffic_country where target_id = ? and domain = ?",
        (target_id, domain))
    res = {e["country_code"]: int(e["traffic"]) for e in organic_traffic}
    return res


def get_analysis_request(analysis_id) -> int:
    select_all("")


def get_domain_dr(target_id: str, domain: str) -> int:
    rating = select_one(
        "SELECT domain_rating FROM batch_analysis WHERE target_id = ? AND domain = ?",
        (target_id, domain),
    )
    return 0 if not rating["domain_rating"] else int(rating["domain_rating"])


def get_domain_categories(target_id: str, domain: str) -> Sequence[CloudFlareCategory]:
    categories = select_all("select id, super_category_id from domain_categories WHERE target_id = ? AND domain = ?",
                     (target_id, domain))
    return [CloudFlareCategory(c['id'], c['super_category_id']) for c in categories]
