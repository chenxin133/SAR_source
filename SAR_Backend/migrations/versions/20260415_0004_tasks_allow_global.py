"""0004 allow global tasks (no image/sample)

Revision ID: 20260415_0004
Revises: 20260415_0003
Create Date: 2026-04-15
"""

from alembic import op

revision = "20260415_0004"
down_revision = "20260415_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE tasks
          DROP CONSTRAINT IF EXISTS tasks_target_xor_chk;
        ALTER TABLE tasks
          ADD CONSTRAINT tasks_target_xor_chk CHECK (num_nonnulls(image_id, sample_id) <= 1);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE tasks
          DROP CONSTRAINT IF EXISTS tasks_target_xor_chk;
        ALTER TABLE tasks
          ADD CONSTRAINT tasks_target_xor_chk CHECK (num_nonnulls(image_id, sample_id) = 1);
        """
    )

