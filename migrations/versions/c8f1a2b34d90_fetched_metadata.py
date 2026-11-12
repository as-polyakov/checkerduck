"""record each domain fetch, including empty snapshots

Revision ID: c8f1a2b34d90
Revises: a91c4e2b6d70
Create Date: 2026-11-11

fetched is the freshness record. Data tables stay empty when a fetch returns
no rows, so existing snapshots are counted into fetched here. Country traffic
shares the batch_analysis snapshot and is not fetched on its own.
"""

from alembic import op

revision = "c8f1a2b34d90"
down_revision = "a91c4e2b6d70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE fetched
        (
            fetched_at    TEXT    NOT NULL,
            domain        TEXT    NOT NULL,
            table_name    TEXT    NOT NULL,
            records_count INTEGER NOT NULL,
            PRIMARY KEY (fetched_at, domain, table_name)
        )
    """)
    op.execute("""
        INSERT INTO fetched (fetched_at, domain, table_name, records_count)
        SELECT fetched_at, domain, 'domain_categories', COUNT(*)
        FROM domain_categories
        GROUP BY fetched_at, domain
    """)
    op.execute("""
        INSERT INTO fetched (fetched_at, domain, table_name, records_count)
        SELECT fetched_at, domain, 'batch_analysis', COUNT(*)
        FROM batch_analysis
        GROUP BY fetched_at, domain
    """)
    op.execute("""
        INSERT INTO fetched (fetched_at, domain, table_name, records_count)
        SELECT fetched_at, domain, 'ahrefs_metrics_history', COUNT(*)
        FROM ahrefs_metrics_history
        GROUP BY fetched_at, domain
    """)
    op.execute("""
        INSERT INTO fetched (fetched_at, domain, table_name, records_count)
        SELECT fetched_at, domain, 'ahrefs_top_pages', COUNT(*)
        FROM ahrefs_top_pages
        GROUP BY fetched_at, domain
    """)
    op.execute("""
        INSERT INTO fetched (fetched_at, domain, table_name, records_count)
        SELECT fetched_at, domain, 'ahrefs_organic_keywords', COUNT(*)
        FROM ahrefs_organic_keywords
        GROUP BY fetched_at, domain
    """)
    op.execute("""
        INSERT INTO fetched (fetched_at, domain, table_name, records_count)
        SELECT fetched_at, domain, 'ahrefs_backlinks', COUNT(*)
        FROM ahrefs_backlinks
        GROUP BY fetched_at, domain
    """)
    op.execute("""
        INSERT INTO fetched (fetched_at, domain, table_name, records_count)
        SELECT fetched_at, domain, 'anchors_forbidden_words', COUNT(*)
        FROM anchors_forbidden_words
        GROUP BY fetched_at, domain
    """)
    op.execute("""
        insert into fetched(fetched_at, domain, table_name, records_count)
        select max(b.fetched_at), b.domain, 'anchors_forbidden_words', 0
        from fetched b left join fetched f
                    on b.domain = f.domain and f.table_name = 'anchors_forbidden_words'
                    where f.fetched_at is null
        group by b.domain
    """)
    op.execute("""
        insert into fetched(fetched_at, domain, table_name, records_count)
        select max(b.fetched_at), b.domain, 'ahrefs_organic_keywords', 0
        from fetched b left join fetched f
                    on b.domain = f.domain and f.table_name = 'ahrefs_organic_keywords'
                    where f.fetched_at is null
        group by b.domain
    """)

def downgrade() -> None:
    op.execute("DROP TABLE fetched")