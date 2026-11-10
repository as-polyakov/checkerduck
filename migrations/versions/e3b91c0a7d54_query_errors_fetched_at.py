"""query_errors keyed by fetched_at

Revision ID: e3b91c0a7d54
Revises: b7e2c9a41f08
Create Date: 2026-11-09

SQLite cannot change a primary key in place. query_errors is recreated.
fetched_at replaces target_id. Existing error rows are dropped.
"""

from alembic import op

revision = "e3b91c0a7d54"
down_revision = "b7e2c9a41f08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE query_errors")
    op.execute("""
        CREATE TABLE query_errors
        (
            fetched_at TEXT NOT NULL,
            domain     TEXT,
            api        TEXT,
            error      TEXT,
            PRIMARY KEY (fetched_at, domain, api)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE query_errors")
    op.execute("""
        CREATE TABLE query_errors
        (
            target_id TEXT NOT NULL,
            domain    TEXT,
            api       TEXT,
            error     TEXT,
            PRIMARY KEY (target_id, domain, api)
        )
    """)
