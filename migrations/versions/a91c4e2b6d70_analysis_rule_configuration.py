"""analysis stores the rule configuration snapshot

Revision ID: a91c4e2b6d70
Revises: e3b91c0a7d54
Create Date: 2026-11-10

The JSON document is the configuration that produced an analysis's rule scores.
Existing rows stay NULL and load as the default configuration.
"""

from alembic import op

revision = "a91c4e2b6d70"
down_revision = "e3b91c0a7d54"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE analysis ADD COLUMN rule_configuration TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE analysis DROP COLUMN rule_configuration")
