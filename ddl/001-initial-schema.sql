-- Enable foreign key constraints in SQLite
PRAGMA foreign_keys = ON;

-- Main table for Ahrefs metrics
CREATE TABLE batch_analysis
(
    target_id               TEXT, -- internal surrogate key

    -- Core identifiers
    domain                  TEXT NOT NULL,
    ip                      TEXT, -- IP address as text
    protocol                TEXT NOT NULL CHECK (protocol IN ('http', 'https', 'both')),
    mode                    TEXT NOT NULL,

    -- Rankings and ratings
    ahrefs_rank             INTEGER,
    domain_rating           REAL, -- up to 100.00 scale
    url_rating              REAL, -- up to 100.00 scale

    -- Backlinks
    backlinks               INTEGER,
    backlinks_dofollow      INTEGER,
    backlinks_internal      INTEGER,
    backlinks_nofollow      INTEGER,
    backlinks_redirect      INTEGER,

    -- Referring domains and IPs
    refdomains              INTEGER,
    refdomains_dofollow     INTEGER,
    refdomains_nofollow     INTEGER,
    refips                  INTEGER,
    refips_subnets          INTEGER,

    -- Linking domains
    linked_domains          INTEGER,
    linked_domains_dofollow INTEGER,

    -- Outgoing links
    outgoing_links          INTEGER,
    outgoing_links_dofollow INTEGER,

    -- Organic traffic & keywords
    org_cost                INTEGER,
    org_traffic             INTEGER,
    org_keywords            INTEGER,
    org_keywords_1_3        INTEGER,
    org_keywords_4_10       INTEGER,
    org_keywords_11_20      INTEGER,
    org_keywords_21_50      INTEGER,
    org_keywords_51_plus    INTEGER,

    -- Paid traffic & keywords
    paid_cost               INTEGER,
    paid_traffic            INTEGER,
    paid_keywords           INTEGER,
    paid_ads                INTEGER,
    lang_by_top_traffic     TEXT,
    domain_category         TEXT,
    detected_lang           TEXT,

    -- Timestamps for auditing
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (target_id, domain)
);

-- Table for top countries by traffic
CREATE TABLE ahrefs_org_traffic_country
(
    target_id    TEXT NOT NULL,
    domain       TEXT NOT NULL,
    country_code TEXT NOT NULL, -- ISO country code (2 chars)
    traffic      INTEGER,
    PRIMARY KEY (target_id, domain, country_code)
);

-- Table for org traffic history
CREATE TABLE ahrefs_metrics_history
(
    target_id    TEXT NOT NULL,
    domain       TEXT NOT NULL,
    country_code TEXT NOT NULL, -- ISO country code (2 chars)
    date         TEXT NOT NULL, --SO-8601 strings (YYYY-MM-DDTHH:MM:SSZ)
    org_cost     INTEGER,
    org_traffic  INTEGER,
    paid_cost    INTEGER,
    paid_traffic INTEGER,
    PRIMARY KEY (target_id, domain, country_code, date)
);


-- Table for top pages
CREATE TABLE ahrefs_top_pages
(
    target_id                       TEXT NOT NULL,
    domain                          TEXT, -- ISO country code (2 chars)
    country_code                    TEXT, -- ISO country code (2 chars)
    date                            TEXT, --SO-8601 strings (YYYY-MM-DDTHH:MM:SSZ)
    position                        INTEGER,
    top_keyword_best_position_title TEXT,
    sum_traffic                     INTEGER,
    PRIMARY KEY (target_id, domain, country_code, date, position)
);

-- Table for organic keywords
CREATE TABLE ahrefs_organic_keywords
(
    target_id                      TEXT NOT NULL,
    domain                         TEXT,
    keyword                        TEXT,
    keyword_country                TEXT,
    date                           TEXT, --SO-8601 strings (YYYY-MM-DDTHH:MM:SSZ)
    forbidden_word_category        TEXT,
    is_best_position_set_top_3     BOOLEAN,
    is_best_position_set_top_4_10  BOOLEAN,
    is_best_position_set_top_11_50 BOOLEAN,
    best_position_url              TEXT,
    PRIMARY KEY (target_id, domain, keyword, keyword_country, date)
);

-- Table for
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

-- Table for top pages
CREATE TABLE query_errors
(
    target_id TEXT NOT NULL,
    domain    TEXT, -- ISO country code (2 chars)
    api       TEXT,
    error     TEXT,
    PRIMARY KEY (target_id, domain, api)
);


-- Table for top pages
CREATE TABLE analysis
(
    target_id         TEXT NOT NULL,
    name              TEXT, -- ISO country code (2 chars)
    status            TEXT,
    processed_domains INTEGER default 0,
    created_at        TEXT,
    completed_at      TEXT,
    PRIMARY KEY (target_id)
);

-- Table for top pages
CREATE TABLE analysis_domains
(
    target_id TEXT NOT NULL,
    domain    TEXT, -- ISO country code (2 chars)
    price_usd integer,
    notes     TEXT,
    PRIMARY KEY (target_id, domain)
);

CREATE TABLE rules_evaluation_results
(
    target_id          TEXT NOT NULL,
    domain             TEXT, -- ISO country code (2 chars)
    rule               text,
    score              int,
    critical_violation BOOLEAN,
    details            TEXT,
    PRIMARY KEY (target_id, domain, rule)
);

