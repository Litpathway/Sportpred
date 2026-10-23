"""Shared model artifacts and canonical league identities.

Revision ID: d8f1c4a072be
Revises: c4f7a90d12ab
"""
from alembic import op
import sqlalchemy as sa

revision = "d8f1c4a072be"
down_revision = "c4f7a90d12ab"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("model_versions", sa.Column("artifact_data", sa.LargeBinary(), nullable=True))
    op.add_column("competitions", sa.Column("league_slug", sa.String(60), nullable=True))
    op.create_index("ix_competitions_league_slug", "competitions", ["league_slug"])


def downgrade():
    op.drop_index("ix_competitions_league_slug", table_name="competitions")
    op.drop_column("competitions", "league_slug")
    op.drop_column("model_versions", "artifact_data")
