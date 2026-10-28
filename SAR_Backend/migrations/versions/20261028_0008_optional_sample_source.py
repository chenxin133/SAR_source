"""Allow manually uploaded samples without a source image."""
from alembic import op
from app.db_types import GUID

revision = "20261028_0008"
down_revision = "20261023_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("samples") as batch:
        batch.alter_column("image_id", existing_type=GUID(), nullable=True)


def downgrade() -> None:
    # Existing unlinked samples must be associated before reverting this schema.
    with op.batch_alter_table("samples") as batch:
        batch.alter_column("image_id", existing_type=GUID(), nullable=False)
