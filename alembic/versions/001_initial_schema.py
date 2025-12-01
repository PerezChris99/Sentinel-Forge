"""Initial schema with TimescaleDB and pgvector

Revision ID: 001_initial_schema
Revises: 
Create Date: 2025-12-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
    
    # Create persons table
    op.create_table(
        'persons',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('role', sa.String(100)),
        sa.Column('details', postgresql.JSON),
        sa.Column('embedding', postgresql.ARRAY(sa.Float), nullable=True),  # Will be vector(128)
        sa.Column('known_status', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('consent_given', sa.Boolean, nullable=False, server_default='false'),
    )
    
    # Modify embedding column to use pgvector
    op.execute("ALTER TABLE persons ALTER COLUMN embedding TYPE vector(128) USING embedding::vector(128)")
    
    # Create sightings table
    op.create_table(
        'sightings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('person_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('persons.id', ondelete='SET NULL'), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('camera_id', sa.String(100), nullable=False),
        sa.Column('confidence', sa.Float, nullable=False),
        sa.Column('embedding', postgresql.ARRAY(sa.Float)),
        sa.Column('face_image_b64', sa.Text),
        sa.Column('flag_level', sa.Integer, nullable=False, server_default='0'),
        sa.Column('metadata', postgresql.JSON),
    )
    
    # Modify embedding column to use pgvector
    op.execute("ALTER TABLE sightings ALTER COLUMN embedding TYPE vector(128) USING embedding::vector(128)")
    
    # Create hypertable on sightings
    op.execute("SELECT create_hypertable('sightings', 'timestamp')")
    
    # Create indexes
    op.create_index('ix_sightings_timestamp', 'sightings', ['timestamp'])
    op.create_index('ix_sightings_camera_id', 'sightings', ['camera_id'])
    op.create_index('ix_sightings_person_timestamp', 'sightings', ['person_id', 'timestamp'])
    
    # Create patterns table
    op.create_table(
        'patterns',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('person_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('persons.id', ondelete='CASCADE'), nullable=False),
        sa.Column('date', sa.DateTime, nullable=False),
        sa.Column('sighting_count', sa.Integer, server_default='0'),
        sa.Column('avg_duration', sa.Float),
        sa.Column('anomaly_score', sa.Float, server_default='0.0'),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )
    
    op.create_index('ix_patterns_date', 'patterns', ['date'])
    
    # Create footage_refs table
    op.create_table(
        'footage_refs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('sighting_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sightings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('video_path', sa.String(500), nullable=False),
        sa.Column('start_frame', sa.Integer, nullable=False),
        sa.Column('duration', sa.Integer),
    )


def downgrade() -> None:
    op.drop_table('footage_refs')
    op.drop_table('patterns')
    op.drop_table('sightings')
    op.drop_table('persons')
    op.execute("DROP EXTENSION IF EXISTS vector CASCADE")
