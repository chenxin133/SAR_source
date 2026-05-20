"""0003 image metadata columns

Revision ID: 20260415_0003
Revises: 20260415_0002
Create Date: 2026-04-15
"""

from alembic import op

revision = "20260415_0003"
down_revision = "20260415_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE images
          ADD COLUMN IF NOT EXISTS satellite text,
          ADD COLUMN IF NOT EXISTS acquisition_at timestamptz,
          ADD COLUMN IF NOT EXISTS resolution text,
          ADD COLUMN IF NOT EXISTS polarization text,
          ADD COLUMN IF NOT EXISTS description text;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE images
          DROP COLUMN IF EXISTS description,
          DROP COLUMN IF EXISTS polarization,
          DROP COLUMN IF EXISTS resolution,
          DROP COLUMN IF EXISTS acquisition_at,
          DROP COLUMN IF EXISTS satellite;
        """
    )

