"""query_errors stores the data table name

Revision ID: d4a7c3e91b20
Revises: c8f1a2b34d90
Create Date: 2026-11-11

The error row names the same table as the insert and the fetched record.
"""

from alembic import op

revision = "d4a7c3e91b20"
down_revision = "c8f1a2b34d90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE query_errors
        SET api = CASE api
            WHEN 'cloudflare_domain_categories' THEN 'domain_categories'
            WHEN 'metrics_history' THEN 'ahrefs_metrics_history'
            WHEN 'top_pages' THEN 'ahrefs_top_pages'
            WHEN 'organic_keywords' THEN 'ahrefs_organic_keywords'
            WHEN 'backlinks' THEN 'ahrefs_backlinks'
            WHEN 'outgoing_anchors' THEN 'anchors_forbidden_words'
            ELSE api
        END
    """)
    op.execute("ALTER TABLE query_errors RENAME COLUMN api TO table_name")


def downgrade() -> None:
    op.execute("ALTER TABLE query_errors RENAME COLUMN table_name TO api")
    op.execute("""
        UPDATE query_errors
        SET api = CASE api
            WHEN 'domain_categories' THEN 'cloudflare_domain_categories'
            WHEN 'ahrefs_metrics_history' THEN 'metrics_history'
            WHEN 'ahrefs_top_pages' THEN 'top_pages'
            WHEN 'ahrefs_organic_keywords' THEN 'organic_keywords'
            WHEN 'ahrefs_backlinks' THEN 'backlinks'
            WHEN 'anchors_forbidden_words' THEN 'outgoing_anchors'
            ELSE api
        END
    """)
