"""baseline

Revision ID: 713b140fbad5
Revises:
Create Date: 2025-09-28 20:59:29.894753
"""

from alembic import op


revision = "713b140fbad5"
down_revision = None
branch_labels = None
depends_on = None


SCHEMA_SQL = """
CREATE TABLE domain_categories
(
    target_id         TEXT NOT NULL,
    domain            TEXT NOT NULL,
    id                TEXT,
    name              TEXT,
    super_category_id TEXT,
    PRIMARY KEY (target_id, domain, id)
);

CREATE TABLE batch_analysis
(
    target_id               TEXT,
    domain                  TEXT NOT NULL,
    ip                      TEXT,
    protocol                TEXT NOT NULL CHECK (protocol IN ('http', 'https', 'both')),
    mode                    TEXT NOT NULL,

    ahrefs_rank             INTEGER,
    domain_rating           REAL,
    url_rating              REAL,

    backlinks               INTEGER,
    backlinks_dofollow      INTEGER,
    backlinks_internal      INTEGER,
    backlinks_nofollow      INTEGER,
    backlinks_redirect      INTEGER,

    refdomains              INTEGER,
    refdomains_dofollow     INTEGER,
    refdomains_nofollow     INTEGER,
    refips                  INTEGER,
    refips_subnets          INTEGER,

    linked_domains          INTEGER,
    linked_domains_dofollow INTEGER,

    outgoing_links          INTEGER,
    outgoing_links_dofollow INTEGER,

    org_cost                INTEGER,
    org_traffic             INTEGER,
    org_keywords            INTEGER,
    org_keywords_1_3        INTEGER,
    org_keywords_4_10       INTEGER,
    org_keywords_11_20      INTEGER,
    org_keywords_21_50      INTEGER,
    org_keywords_51_plus    INTEGER,

    paid_cost               INTEGER,
    paid_traffic            INTEGER,
    paid_keywords           INTEGER,
    paid_ads                INTEGER,
    lang_by_top_traffic     TEXT,
    domain_category         TEXT,
    detected_lang           TEXT,

    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (target_id, domain)
);

CREATE TABLE ahrefs_org_traffic_country
(
    target_id    TEXT NOT NULL,
    domain       TEXT NOT NULL,
    country_code TEXT NOT NULL,
    traffic      INTEGER,
    PRIMARY KEY (target_id, domain, country_code)
);

CREATE TABLE ahrefs_metrics_history
(
    target_id    TEXT NOT NULL,
    domain       TEXT NOT NULL,
    country_code TEXT NOT NULL,
    date         TEXT NOT NULL,
    org_cost     INTEGER,
    org_traffic  INTEGER,
    paid_cost    INTEGER,
    paid_traffic INTEGER,
    PRIMARY KEY (target_id, domain, country_code, date)
);

CREATE TABLE ahrefs_top_pages
(
    target_id                       TEXT NOT NULL,
    domain                          TEXT,
    country_code                    TEXT,
    date                            TEXT,
    position                        INTEGER,
    top_keyword_best_position_title TEXT,
    sum_traffic                     INTEGER,
    PRIMARY KEY (target_id, domain, country_code, date, position)
);

CREATE TABLE ahrefs_organic_keywords
(
    target_id                      TEXT NOT NULL,
    domain                         TEXT,
    keyword                        TEXT,
    keyword_country                TEXT,
    date                           TEXT,
    forbidden_word_category        TEXT,
    is_best_position_set_top_3     BOOLEAN,
    is_best_position_set_top_4_10  BOOLEAN,
    is_best_position_set_top_11_50 BOOLEAN,
    best_position_url              TEXT,
    PRIMARY KEY (target_id, domain, keyword, keyword_country, date)
);

CREATE TABLE ahrefs_backlinks
(
    target_id                    TEXT NOT NULL,
    domain                       TEXT,
    ahrefs_rank_source           INTEGER,
    ahrefs_rank_target           INTEGER,
    alt                          TEXT,
    anchor                       TEXT,
    forbidden_word_category      TEXT,
    broken_redirect_new_target   TEXT,
    broken_redirect_reason       TEXT,
    broken_redirect_source       TEXT,
    class_c                      INTEGER,
    discovered_status            TEXT,
    domain_rating_source         REAL,
    domain_rating_target         REAL,
    drop_reason                  TEXT,
    encoding                     TEXT,
    first_seen                   TEXT,
    first_seen_link              TEXT,
    http_code                    INTEGER,
    http_crawl                   BOOLEAN,
    ip_source                    TEXT,
    is_alternate                 BOOLEAN,
    is_canonical                 BOOLEAN,
    is_content                   BOOLEAN,
    is_dofollow                  BOOLEAN,
    is_form                      BOOLEAN,
    is_frame                     BOOLEAN,
    is_image                     BOOLEAN,
    is_lost                      BOOLEAN,
    is_new                       BOOLEAN,
    is_nofollow                  BOOLEAN,
    is_redirect                  BOOLEAN,
    is_redirect_lost             BOOLEAN,
    is_root_source               BOOLEAN,
    is_root_target               BOOLEAN,
    is_rss                       BOOLEAN,
    is_spam                      BOOLEAN,
    is_sponsored                 BOOLEAN,
    is_text                      BOOLEAN,
    is_ugc                       BOOLEAN,
    js_crawl                     BOOLEAN,
    last_seen                    TEXT,
    last_visited                 TEXT,
    link_group_count             INTEGER,
    link_type                    TEXT,
    linked_domains_source_domain INTEGER,
    linked_domains_source_page   INTEGER,
    linked_domains_target_domain INTEGER,
    links_external               INTEGER,
    links_internal               INTEGER,
    lost_reason                  TEXT,
    name_source                  TEXT,
    name_target                  TEXT,
    noindex                      BOOLEAN,
    page_category_source         TEXT,
    page_size                    INTEGER,
    page_type_source             TEXT,
    port_source                  INTEGER,
    port_target                  INTEGER,
    positions                    INTEGER,
    redirect_code                INTEGER,
    refdomains_source            INTEGER,
    refdomains_source_domain     INTEGER,
    refdomains_target_domain     INTEGER,
    root_name_source             TEXT,
    root_name_target             TEXT,
    snippet_left                 TEXT,
    snippet_right                TEXT,
    source_page_author           TEXT,
    source_page_publish_date     TEXT,
    title                        TEXT,
    tld_class_source             TEXT,
    tld_class_target             TEXT,
    traffic                      INTEGER,
    traffic_domain               INTEGER,
    url_from                     TEXT,
    url_from_plain               TEXT,
    url_rating_source            REAL,
    url_to                       TEXT,
    PRIMARY KEY (target_id, domain, url_from)
);

CREATE TABLE anchors_forbidden_words
(
    target_id               TEXT NOT NULL,
    domain                  TEXT,
    direction               TEXT,
    anchor                  TEXT,
    forbidden_word_category TEXT,
    title                   TEXT,
    url_from                TEXT,
    snippet_left            TEXT,
    snippet_right           TEXT,
    PRIMARY KEY (target_id, domain, direction, anchor, url_from)
);

CREATE TABLE query_errors
(
    target_id TEXT NOT NULL,
    domain    TEXT,
    api       TEXT,
    error     TEXT,
    PRIMARY KEY (target_id, domain, api)
);

CREATE TABLE analysis
(
    target_id         TEXT NOT NULL,
    name              TEXT,
    status            TEXT,
    processed_domains INTEGER DEFAULT 0,
    created_at        TEXT,
    completed_at      TEXT,
    PRIMARY KEY (target_id)
);

CREATE TABLE analysis_domains
(
    target_id TEXT NOT NULL,
    domain    TEXT,
    price_usd INTEGER,
    notes     TEXT,
    PRIMARY KEY (target_id, domain)
);

CREATE TABLE rules_evaluation_results
(
    target_id          TEXT NOT NULL,
    domain             TEXT,
    rule               TEXT,
    score              INTEGER,
    critical_violation BOOLEAN,
    details             TEXT,
    PRIMARY KEY (target_id, domain, rule)
);
"""


def upgrade() -> None:
    # SQLite PRAGMA foreign_keys is connection-specific.
    # Enable it separately if your application uses foreign keys.
    for statement in SCHEMA_SQL.split(";"):
        statement = statement.strip()
        if statement:
            op.execute(statement)


def downgrade() -> None:
    # Drop tables in reverse dependency order if foreign keys are added.
    op.execute("DROP TABLE rules_evaluation_results")
    op.execute("DROP TABLE analysis_domains")
    op.execute("DROP TABLE analysis")
    op.execute("DROP TABLE query_errors")
    op.execute("DROP TABLE anchors_forbidden_words")
    op.execute("DROP TABLE ahrefs_backlinks")
    op.execute("DROP TABLE ahrefs_organic_keywords")
    op.execute("DROP TABLE ahrefs_top_pages")
    op.execute("DROP TABLE ahrefs_metrics_history")
    op.execute("DROP TABLE ahrefs_org_traffic_country")
    op.execute("DROP TABLE batch_analysis")
    op.execute("DROP TABLE domain_categories")