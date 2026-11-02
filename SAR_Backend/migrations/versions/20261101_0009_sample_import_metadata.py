"""Persist standalone sample resolution and file fingerprints."""
from alembic import op
import sqlalchemy as sa

revision = "20261101_0009"
down_revision = "20261028_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("samples", sa.Column("resolution", sa.Text(), nullable=True))
    op.add_column("samples", sa.Column("checksum_sha256", sa.String(64), nullable=True))
    op.create_index("ix_samples_project_checksum", "samples", ["project_id", "checksum_sha256"])


def downgrade() -> None:
    op.drop_index("ix_samples_project_checksum", table_name="samples")
    with op.batch_alter_table("samples") as batch:
        batch.drop_column("checksum_sha256")
        batch.drop_column("resolution")
