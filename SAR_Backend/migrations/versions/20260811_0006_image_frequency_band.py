"""add image frequency band metadata

Revision ID: 20260811_0006
Revises: 20260415_0005
"""

import sqlalchemy as sa
from alembic import op


revision = "20260811_0006"
down_revision = "20260415_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("images", sa.Column("frequency_band", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("images", "frequency_band")
