"""Preserve prediction snapshots across scheduled inference runs."""
from alembic import op
import sqlalchemy as sa

revision = "c4f7a90d12ab"
down_revision = "b3ea9ca2264b"
branch_labels = None
depends_on = None


def upgrade():
    constraints = sa.inspect(op.get_bind()).get_unique_constraints("predictions")
    previous = next(c for c in constraints if set(c["column_names"]) == {"fixture_id", "model_id", "market"})
    convention = {"uq": "uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s_%(column_2_name)s"}
    with op.batch_alter_table("predictions", naming_convention=convention) as batch:
        batch.add_column(sa.Column("generation", sa.String(40), server_default="initial", nullable=False))
        batch.drop_constraint(previous["name"] or "uq_predictions_fixture_id_model_id_market", type_="unique")
        batch.create_unique_constraint("uq_prediction_generation", ["fixture_id", "model_id", "market", "generation"])


def downgrade():
    # Keep the most recent snapshot per fixture/model/market before restoring
    # the original uniqueness rule. Operators should back up before downgrade.
    predictions = sa.table("predictions", sa.column("id"), sa.column("fixture_id"), sa.column("model_id"), sa.column("market"))
    keep = sa.select(sa.func.max(predictions.c.id)).group_by(predictions.c.fixture_id, predictions.c.model_id, predictions.c.market)
    op.execute(predictions.delete().where(predictions.c.id.not_in(keep)))
    with op.batch_alter_table("predictions") as batch:
        batch.drop_constraint("uq_prediction_generation", type_="unique")
        batch.drop_column("generation")
        batch.create_unique_constraint("uq_predictions_fixture_id_model_id_market", ["fixture_id", "model_id", "market"])
