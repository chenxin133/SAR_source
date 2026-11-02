"""Archive scene XML and persist sample naming metadata."""
from alembic import op
import sqlalchemy as sa

revision = '20261102_0010'
down_revision = '20261101_0009'
branch_labels = None
depends_on = None


def upgrade():
    for table, columns in {
        'images': [('metadata_xml_key', sa.Text()), ('metadata_xml_filename', sa.Text()), ('scene_metadata', sa.JSON())],
        'samples': [('frequency_band', sa.Text()), ('sequence_no', sa.Integer()), ('metadata_xml_key', sa.Text()), ('scene_metadata', sa.JSON())],
    }.items():
        for name, kind in columns:
            op.add_column(table, sa.Column(name, kind, nullable=True))
    op.create_index('ux_samples_project_sequence', 'samples', ['project_id', 'sequence_no'], unique=True)


def downgrade():
    op.drop_index('ux_samples_project_sequence', table_name='samples')
    for table, columns in {'images': ['metadata_xml_key', 'metadata_xml_filename', 'scene_metadata'],
                           'samples': ['frequency_band', 'sequence_no', 'metadata_xml_key', 'scene_metadata']}.items():
        with op.batch_alter_table(table) as batch:
            for name in columns:
                batch.drop_column(name)
