"""domain snapshots keyed by fetched_at

Revision ID: b7e2c9a41f08
Revises: 713b140fbad5
Create Date: 2026-11-08

SQLite cannot change a primary key in place, so each data table is recreated.
fetched_at replaces target_id. analysis, analysis_domains,
rules_evaluation_results, and query_errors stay as they are.
"""

from alembic import op

revision = "b7e2c9a41f08"
down_revision = "713b140fbad5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE domain_categories__new (
            fetched_at        TEXT NOT NULL,
            domain            TEXT NOT NULL,
            id                TEXT,
            name              TEXT,
            super_category_id TEXT,
            PRIMARY KEY (domain, fetched_at, id)
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO domain_categories__new (
            fetched_at, domain, id, name, super_category_id
        )
        SELECT
            COALESCE(strftime('%Y-%m-%dT%H:%M:00+00:00', a.created_at), '1970-01-01T00:00:00+00:00'),
            t.domain, t.id, t.name, t.super_category_id
        FROM domain_categories t
        LEFT JOIN analysis a ON a.target_id = t.target_id
        ORDER BY a.created_at
    """)
    op.execute("DROP TABLE domain_categories")
    op.execute("ALTER TABLE domain_categories__new RENAME TO domain_categories")

    op.execute("""
        CREATE TABLE batch_analysis__new (
            fetched_at              TEXT NOT NULL,
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
            PRIMARY KEY (domain, fetched_at)
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO batch_analysis__new (
            fetched_at, domain, ip, protocol, mode,
            ahrefs_rank, domain_rating, url_rating,
            backlinks, backlinks_dofollow, backlinks_internal, backlinks_nofollow, backlinks_redirect,
            refdomains, refdomains_dofollow, refdomains_nofollow, refips, refips_subnets,
            linked_domains, linked_domains_dofollow,
            outgoing_links, outgoing_links_dofollow,
            org_cost, org_traffic, org_keywords,
            org_keywords_1_3, org_keywords_4_10, org_keywords_11_20, org_keywords_21_50, org_keywords_51_plus,
            paid_cost, paid_traffic, paid_keywords, paid_ads,
            lang_by_top_traffic, domain_category, detected_lang,
            created_at, updated_at
        )
        SELECT
            COALESCE(strftime('%Y-%m-%dT%H:%M:00+00:00', a.created_at), '1970-01-01T00:00:00+00:00'),
            t.domain, t.ip, t.protocol, t.mode,
            t.ahrefs_rank, t.domain_rating, t.url_rating,
            t.backlinks, t.backlinks_dofollow, t.backlinks_internal, t.backlinks_nofollow, t.backlinks_redirect,
            t.refdomains, t.refdomains_dofollow, t.refdomains_nofollow, t.refips, t.refips_subnets,
            t.linked_domains, t.linked_domains_dofollow,
            t.outgoing_links, t.outgoing_links_dofollow,
            t.org_cost, t.org_traffic, t.org_keywords,
            t.org_keywords_1_3, t.org_keywords_4_10, t.org_keywords_11_20, t.org_keywords_21_50, t.org_keywords_51_plus,
            t.paid_cost, t.paid_traffic, t.paid_keywords, t.paid_ads,
            t.lang_by_top_traffic, t.domain_category, t.detected_lang,
            t.created_at, t.updated_at
        FROM batch_analysis t
        LEFT JOIN analysis a ON a.target_id = t.target_id
        ORDER BY a.created_at
    """)
    op.execute("DROP TABLE batch_analysis")
    op.execute("ALTER TABLE batch_analysis__new RENAME TO batch_analysis")

    op.execute("""
        CREATE TABLE ahrefs_org_traffic_country__new (
            fetched_at   TEXT NOT NULL,
            domain       TEXT NOT NULL,
            country_code TEXT NOT NULL,
            traffic      INTEGER,
            PRIMARY KEY (domain, fetched_at, country_code)
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO ahrefs_org_traffic_country__new (
            fetched_at, domain, country_code, traffic
        )
        SELECT
            COALESCE(strftime('%Y-%m-%dT%H:%M:00+00:00', a.created_at), '1970-01-01T00:00:00+00:00'),
            t.domain, t.country_code, t.traffic
        FROM ahrefs_org_traffic_country t
        LEFT JOIN analysis a ON a.target_id = t.target_id
        ORDER BY a.created_at
    """)
    op.execute("DROP TABLE ahrefs_org_traffic_country")
    op.execute("ALTER TABLE ahrefs_org_traffic_country__new RENAME TO ahrefs_org_traffic_country")

    op.execute("""
        CREATE TABLE ahrefs_metrics_history__new (
            fetched_at   TEXT NOT NULL,
            domain       TEXT NOT NULL,
            date         TEXT NOT NULL,
            org_cost     INTEGER,
            org_traffic  INTEGER,
            paid_cost    INTEGER,
            paid_traffic INTEGER,
            PRIMARY KEY (domain, fetched_at, date)
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO ahrefs_metrics_history__new (
            fetched_at, domain, date, org_cost, org_traffic, paid_cost, paid_traffic
        )
        SELECT
            COALESCE(strftime('%Y-%m-%dT%H:%M:00+00:00', a.created_at), '1970-01-01T00:00:00+00:00'),
            t.domain, t.date, t.org_cost, t.org_traffic, t.paid_cost, t.paid_traffic
        FROM ahrefs_metrics_history t
        LEFT JOIN analysis a ON a.target_id = t.target_id
        ORDER BY a.created_at
    """)
    op.execute("DROP TABLE ahrefs_metrics_history")
    op.execute("ALTER TABLE ahrefs_metrics_history__new RENAME TO ahrefs_metrics_history")

    op.execute("""
        CREATE TABLE ahrefs_top_pages__new (
            fetched_at                      TEXT NOT NULL,
            domain                          TEXT,
            country_code                    TEXT,
            date                            TEXT,
            position                        INTEGER,
            top_keyword_best_position_title TEXT,
            sum_traffic                     INTEGER,
            PRIMARY KEY (domain, fetched_at, country_code, date, position)
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO ahrefs_top_pages__new (
            fetched_at, domain, country_code, date, position,
            top_keyword_best_position_title, sum_traffic
        )
        SELECT
            COALESCE(strftime('%Y-%m-%dT%H:%M:00+00:00', a.created_at), '1970-01-01T00:00:00+00:00'),
            t.domain, t.country_code, t.date, t.position,
            t.top_keyword_best_position_title, t.sum_traffic
        FROM ahrefs_top_pages t
        LEFT JOIN analysis a ON a.target_id = t.target_id
        ORDER BY a.created_at
    """)
    op.execute("DROP TABLE ahrefs_top_pages")
    op.execute("ALTER TABLE ahrefs_top_pages__new RENAME TO ahrefs_top_pages")

    op.execute("""
        CREATE TABLE ahrefs_organic_keywords__new (
            fetched_at                     TEXT NOT NULL,
            domain                         TEXT,
            keyword                        TEXT,
            keyword_country                TEXT,
            date                           TEXT,
            forbidden_word_category        TEXT,
            is_best_position_set_top_3     BOOLEAN,
            is_best_position_set_top_4_10  BOOLEAN,
            is_best_position_set_top_11_50 BOOLEAN,
            best_position_url              TEXT,
            PRIMARY KEY (domain, fetched_at, keyword, keyword_country, date)
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO ahrefs_organic_keywords__new (
            fetched_at, domain, keyword, keyword_country, date,
            forbidden_word_category,
            is_best_position_set_top_3, is_best_position_set_top_4_10, is_best_position_set_top_11_50,
            best_position_url
        )
        SELECT
            COALESCE(strftime('%Y-%m-%dT%H:%M:00+00:00', a.created_at), '1970-01-01T00:00:00+00:00'),
            t.domain, t.keyword, t.keyword_country, t.date,
            t.forbidden_word_category,
            t.is_best_position_set_top_3, t.is_best_position_set_top_4_10, t.is_best_position_set_top_11_50,
            t.best_position_url
        FROM ahrefs_organic_keywords t
        LEFT JOIN analysis a ON a.target_id = t.target_id
        ORDER BY a.created_at
    """)
    op.execute("DROP TABLE ahrefs_organic_keywords")
    op.execute("ALTER TABLE ahrefs_organic_keywords__new RENAME TO ahrefs_organic_keywords")

    op.execute("""
        CREATE TABLE ahrefs_backlinks__new (
            fetched_at                   TEXT NOT NULL,
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
            PRIMARY KEY (domain, fetched_at, url_from)
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO ahrefs_backlinks__new (
            fetched_at, domain,
            ahrefs_rank_source, ahrefs_rank_target, alt, anchor, forbidden_word_category,
            broken_redirect_new_target, broken_redirect_reason, broken_redirect_source,
            class_c, discovered_status, domain_rating_source, domain_rating_target, drop_reason,
            encoding, first_seen, first_seen_link, http_code, http_crawl, ip_source,
            is_alternate, is_canonical, is_content, is_dofollow, is_form, is_frame, is_image,
            is_lost, is_new, is_nofollow, is_redirect, is_redirect_lost,
            is_root_source, is_root_target, is_rss, is_spam, is_sponsored, is_text, is_ugc,
            js_crawl, last_seen, last_visited, link_group_count, link_type,
            linked_domains_source_domain, linked_domains_source_page, linked_domains_target_domain,
            links_external, links_internal, lost_reason, name_source, name_target,
            noindex, page_category_source, page_size, page_type_source,
            port_source, port_target, positions, redirect_code,
            refdomains_source, refdomains_source_domain, refdomains_target_domain,
            root_name_source, root_name_target, snippet_left, snippet_right,
            source_page_author, source_page_publish_date, title,
            tld_class_source, tld_class_target, traffic, traffic_domain,
            url_from, url_from_plain, url_rating_source, url_to
        )
        SELECT
            COALESCE(strftime('%Y-%m-%dT%H:%M:00+00:00', a.created_at), '1970-01-01T00:00:00+00:00'),
            t.domain,
            t.ahrefs_rank_source, t.ahrefs_rank_target, t.alt, t.anchor, t.forbidden_word_category,
            t.broken_redirect_new_target, t.broken_redirect_reason, t.broken_redirect_source,
            t.class_c, t.discovered_status, t.domain_rating_source, t.domain_rating_target, t.drop_reason,
            t.encoding, t.first_seen, t.first_seen_link, t.http_code, t.http_crawl, t.ip_source,
            t.is_alternate, t.is_canonical, t.is_content, t.is_dofollow, t.is_form, t.is_frame, t.is_image,
            t.is_lost, t.is_new, t.is_nofollow, t.is_redirect, t.is_redirect_lost,
            t.is_root_source, t.is_root_target, t.is_rss, t.is_spam, t.is_sponsored, t.is_text, t.is_ugc,
            t.js_crawl, t.last_seen, t.last_visited, t.link_group_count, t.link_type,
            t.linked_domains_source_domain, t.linked_domains_source_page, t.linked_domains_target_domain,
            t.links_external, t.links_internal, t.lost_reason, t.name_source, t.name_target,
            t.noindex, t.page_category_source, t.page_size, t.page_type_source,
            t.port_source, t.port_target, t.positions, t.redirect_code,
            t.refdomains_source, t.refdomains_source_domain, t.refdomains_target_domain,
            t.root_name_source, t.root_name_target, t.snippet_left, t.snippet_right,
            t.source_page_author, t.source_page_publish_date, t.title,
            t.tld_class_source, t.tld_class_target, t.traffic, t.traffic_domain,
            t.url_from, t.url_from_plain, t.url_rating_source, t.url_to
        FROM ahrefs_backlinks t
        LEFT JOIN analysis a ON a.target_id = t.target_id
        ORDER BY a.created_at
    """)
    op.execute("DROP TABLE ahrefs_backlinks")
    op.execute("ALTER TABLE ahrefs_backlinks__new RENAME TO ahrefs_backlinks")

    op.execute("""
        CREATE TABLE anchors_forbidden_words__new (
            fetched_at              TEXT NOT NULL,
            domain                  TEXT,
            direction               TEXT,
            anchor                  TEXT,
            forbidden_word_category TEXT,
            title                   TEXT,
            url_from                TEXT,
            snippet_left            TEXT,
            snippet_right           TEXT,
            PRIMARY KEY (domain, fetched_at, direction, anchor, url_from)
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO anchors_forbidden_words__new (
            fetched_at, domain, direction, anchor, forbidden_word_category,
            title, url_from, snippet_left, snippet_right
        )
        SELECT
            COALESCE(strftime('%Y-%m-%dT%H:%M:00+00:00', a.created_at), '1970-01-01T00:00:00+00:00'),
            t.domain, t.direction, t.anchor, t.forbidden_word_category,
            t.title, t.url_from, t.snippet_left, t.snippet_right
        FROM anchors_forbidden_words t
        LEFT JOIN analysis a ON a.target_id = t.target_id
        ORDER BY a.created_at
    """)
    op.execute("DROP TABLE anchors_forbidden_words")
    op.execute("ALTER TABLE anchors_forbidden_words__new RENAME TO anchors_forbidden_words")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE anchors_forbidden_words__old (
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
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO anchors_forbidden_words__old (
            target_id, domain, direction, anchor, forbidden_word_category,
            title, url_from, snippet_left, snippet_right
        )
        SELECT
            'migrated',
            domain, direction, anchor, forbidden_word_category,
            title, url_from, snippet_left, snippet_right
        FROM anchors_forbidden_words
        ORDER BY fetched_at
    """)
    op.execute("DROP TABLE anchors_forbidden_words")
    op.execute("ALTER TABLE anchors_forbidden_words__old RENAME TO anchors_forbidden_words")

    op.execute("""
        CREATE TABLE ahrefs_backlinks__old (
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
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO ahrefs_backlinks__old (
            target_id, domain,
            ahrefs_rank_source, ahrefs_rank_target, alt, anchor, forbidden_word_category,
            broken_redirect_new_target, broken_redirect_reason, broken_redirect_source,
            class_c, discovered_status, domain_rating_source, domain_rating_target, drop_reason,
            encoding, first_seen, first_seen_link, http_code, http_crawl, ip_source,
            is_alternate, is_canonical, is_content, is_dofollow, is_form, is_frame, is_image,
            is_lost, is_new, is_nofollow, is_redirect, is_redirect_lost,
            is_root_source, is_root_target, is_rss, is_spam, is_sponsored, is_text, is_ugc,
            js_crawl, last_seen, last_visited, link_group_count, link_type,
            linked_domains_source_domain, linked_domains_source_page, linked_domains_target_domain,
            links_external, links_internal, lost_reason, name_source, name_target,
            noindex, page_category_source, page_size, page_type_source,
            port_source, port_target, positions, redirect_code,
            refdomains_source, refdomains_source_domain, refdomains_target_domain,
            root_name_source, root_name_target, snippet_left, snippet_right,
            source_page_author, source_page_publish_date, title,
            tld_class_source, tld_class_target, traffic, traffic_domain,
            url_from, url_from_plain, url_rating_source, url_to
        )
        SELECT
            'migrated', domain,
            ahrefs_rank_source, ahrefs_rank_target, alt, anchor, forbidden_word_category,
            broken_redirect_new_target, broken_redirect_reason, broken_redirect_source,
            class_c, discovered_status, domain_rating_source, domain_rating_target, drop_reason,
            encoding, first_seen, first_seen_link, http_code, http_crawl, ip_source,
            is_alternate, is_canonical, is_content, is_dofollow, is_form, is_frame, is_image,
            is_lost, is_new, is_nofollow, is_redirect, is_redirect_lost,
            is_root_source, is_root_target, is_rss, is_spam, is_sponsored, is_text, is_ugc,
            js_crawl, last_seen, last_visited, link_group_count, link_type,
            linked_domains_source_domain, linked_domains_source_page, linked_domains_target_domain,
            links_external, links_internal, lost_reason, name_source, name_target,
            noindex, page_category_source, page_size, page_type_source,
            port_source, port_target, positions, redirect_code,
            refdomains_source, refdomains_source_domain, refdomains_target_domain,
            root_name_source, root_name_target, snippet_left, snippet_right,
            source_page_author, source_page_publish_date, title,
            tld_class_source, tld_class_target, traffic, traffic_domain,
            url_from, url_from_plain, url_rating_source, url_to
        FROM ahrefs_backlinks
        ORDER BY fetched_at
    """)
    op.execute("DROP TABLE ahrefs_backlinks")
    op.execute("ALTER TABLE ahrefs_backlinks__old RENAME TO ahrefs_backlinks")

    op.execute("""
        CREATE TABLE ahrefs_organic_keywords__old (
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
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO ahrefs_organic_keywords__old (
            target_id, domain, keyword, keyword_country, date,
            forbidden_word_category,
            is_best_position_set_top_3, is_best_position_set_top_4_10, is_best_position_set_top_11_50,
            best_position_url
        )
        SELECT
            'migrated', domain, keyword, keyword_country, date,
            forbidden_word_category,
            is_best_position_set_top_3, is_best_position_set_top_4_10, is_best_position_set_top_11_50,
            best_position_url
        FROM ahrefs_organic_keywords
        ORDER BY fetched_at
    """)
    op.execute("DROP TABLE ahrefs_organic_keywords")
    op.execute("ALTER TABLE ahrefs_organic_keywords__old RENAME TO ahrefs_organic_keywords")

    op.execute("""
        CREATE TABLE ahrefs_top_pages__old (
            target_id                       TEXT NOT NULL,
            domain                          TEXT,
            country_code                    TEXT,
            date                            TEXT,
            position                        INTEGER,
            top_keyword_best_position_title TEXT,
            sum_traffic                     INTEGER,
            PRIMARY KEY (target_id, domain, country_code, date, position)
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO ahrefs_top_pages__old (
            target_id, domain, country_code, date, position,
            top_keyword_best_position_title, sum_traffic
        )
        SELECT
            'migrated', domain, country_code, date, position,
            top_keyword_best_position_title, sum_traffic
        FROM ahrefs_top_pages
        ORDER BY fetched_at
    """)
    op.execute("DROP TABLE ahrefs_top_pages")
    op.execute("ALTER TABLE ahrefs_top_pages__old RENAME TO ahrefs_top_pages")

    op.execute("""
        CREATE TABLE ahrefs_metrics_history__old (
            target_id    TEXT NOT NULL,
            domain       TEXT NOT NULL,
            date         TEXT NOT NULL,
            org_cost     INTEGER,
            org_traffic  INTEGER,
            paid_cost    INTEGER,
            paid_traffic INTEGER,
            PRIMARY KEY (target_id, domain, date)
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO ahrefs_metrics_history__old (
            target_id, domain, date, org_cost, org_traffic, paid_cost, paid_traffic
        )
        SELECT
            'migrated', domain, date, org_cost, org_traffic, paid_cost, paid_traffic
        FROM ahrefs_metrics_history
        ORDER BY fetched_at
    """)
    op.execute("DROP TABLE ahrefs_metrics_history")
    op.execute("ALTER TABLE ahrefs_metrics_history__old RENAME TO ahrefs_metrics_history")

    op.execute("""
        CREATE TABLE ahrefs_org_traffic_country__old (
            target_id    TEXT NOT NULL,
            domain       TEXT NOT NULL,
            country_code TEXT NOT NULL,
            traffic      INTEGER,
            PRIMARY KEY (target_id, domain, country_code)
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO ahrefs_org_traffic_country__old (
            target_id, domain, country_code, traffic
        )
        SELECT 'migrated', domain, country_code, traffic
        FROM ahrefs_org_traffic_country
        ORDER BY fetched_at
    """)
    op.execute("DROP TABLE ahrefs_org_traffic_country")
    op.execute("ALTER TABLE ahrefs_org_traffic_country__old RENAME TO ahrefs_org_traffic_country")

    op.execute("""
        CREATE TABLE batch_analysis__old (
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
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO batch_analysis__old (
            target_id, domain, ip, protocol, mode,
            ahrefs_rank, domain_rating, url_rating,
            backlinks, backlinks_dofollow, backlinks_internal, backlinks_nofollow, backlinks_redirect,
            refdomains, refdomains_dofollow, refdomains_nofollow, refips, refips_subnets,
            linked_domains, linked_domains_dofollow,
            outgoing_links, outgoing_links_dofollow,
            org_cost, org_traffic, org_keywords,
            org_keywords_1_3, org_keywords_4_10, org_keywords_11_20, org_keywords_21_50, org_keywords_51_plus,
            paid_cost, paid_traffic, paid_keywords, paid_ads,
            lang_by_top_traffic, domain_category, detected_lang,
            created_at, updated_at
        )
        SELECT
            'migrated', domain, ip, protocol, mode,
            ahrefs_rank, domain_rating, url_rating,
            backlinks, backlinks_dofollow, backlinks_internal, backlinks_nofollow, backlinks_redirect,
            refdomains, refdomains_dofollow, refdomains_nofollow, refips, refips_subnets,
            linked_domains, linked_domains_dofollow,
            outgoing_links, outgoing_links_dofollow,
            org_cost, org_traffic, org_keywords,
            org_keywords_1_3, org_keywords_4_10, org_keywords_11_20, org_keywords_21_50, org_keywords_51_plus,
            paid_cost, paid_traffic, paid_keywords, paid_ads,
            lang_by_top_traffic, domain_category, detected_lang,
            created_at, updated_at
        FROM batch_analysis
        ORDER BY fetched_at
    """)
    op.execute("DROP TABLE batch_analysis")
    op.execute("ALTER TABLE batch_analysis__old RENAME TO batch_analysis")

    op.execute("""
        CREATE TABLE domain_categories__old (
            target_id         TEXT NOT NULL,
            domain            TEXT NOT NULL,
            id                TEXT,
            name              TEXT,
            super_category_id TEXT,
            PRIMARY KEY (target_id, domain, id)
        )
    """)
    op.execute("""
        INSERT OR REPLACE INTO domain_categories__old (
            target_id, domain, id, name, super_category_id
        )
        SELECT 'migrated', domain, id, name, super_category_id
        FROM domain_categories
        ORDER BY fetched_at
    """)
    op.execute("DROP TABLE domain_categories")
    op.execute("ALTER TABLE domain_categories__old RENAME TO domain_categories")
