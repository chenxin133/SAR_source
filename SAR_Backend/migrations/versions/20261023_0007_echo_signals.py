"""Create echo signal management table.

Revision ID: 20261023_0007
Revises: 20260811_0006
"""
from alembic import op
import sqlalchemy as sa

from app.db_types import GUID
from app.sa_types import JsonType

revision = "20261023_0007"
down_revision = "20260811_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "echo_signals",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("project_id", GUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("remark", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("frequency_band", sa.Text()),
        sa.Column("center_frequency_ghz", sa.Float()),
        sa.Column("na", sa.Integer(), nullable=False),
        sa.Column("nr", sa.Integer(), nullable=False),
        sa.Column("byte_order", sa.Text(), nullable=False),
        sa.Column("iq_offset", sa.Integer(), nullable=False),
        sa.Column("gate_min", sa.BigInteger(), nullable=False),
        sa.Column("gate_max", sa.BigInteger(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("preview_key", sa.Text(), nullable=False),
        sa.Column("simulation", JsonType),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("na > 0 AND nr > 0", name="echo_dimensions_positive"),
        sa.CheckConstraint("source IN ('imported','simulated')", name="echo_source_valid"),
        sa.CheckConstraint("byte_order IN ('little','big')", name="echo_byte_order_valid"),
        sa.CheckConstraint("iq_offset IN (0,32768)", name="echo_iq_offset_valid"),
    )
    op.create_index("ix_echo_project_created", "echo_signals", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_table("echo_signals")
