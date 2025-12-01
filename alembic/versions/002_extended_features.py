"""
Add extended features: auth, cameras, alerts, incidents

Revision ID: 002_extended_features
Revises: 001_initial_schema
Create Date: 2025-12-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '002_extended_features'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('username', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.Enum('ADMIN', 'OPERATOR', 'VIEWER', name='userrole'), nullable=False),
        sa.Column('full_name', sa.String(255)),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('last_login', sa.DateTime),
        sa.Column('metadata', postgresql.JSONB),
    )

    # Cameras table
    op.create_table(
        'cameras',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('camera_id', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('stream_url', sa.String(500), nullable=False),
        sa.Column('location', sa.String(255)),
        sa.Column('zone', sa.String(100)),
        sa.Column('status', sa.Enum('ONLINE', 'OFFLINE', 'ERROR', 'DISABLED', name='camerastatus'), nullable=False),
        sa.Column('is_enabled', sa.Boolean, default=True, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('last_seen', sa.DateTime),
        sa.Column('metadata', postgresql.JSONB),
    )

    # Alerts table
    op.create_table(
        'alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('sighting_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sightings.id', ondelete='CASCADE')),
        sa.Column('alert_type', sa.String(50), nullable=False),
        sa.Column('severity', sa.Integer, default=1, nullable=False),
        sa.Column('status', sa.Enum('NEW', 'ACKNOWLEDGED', 'DISMISSED', 'ESCALATED', name='alertstatus'), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, index=True),
        sa.Column('acknowledged_at', sa.DateTime),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('resolved_at', sa.DateTime),
        sa.Column('notes', sa.Text),
        sa.Column('metadata', postgresql.JSONB),
    )

    # Incidents table
    op.create_table(
        'incidents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('person_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('persons.id', ondelete='SET NULL')),
        sa.Column('camera_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cameras.id', ondelete='SET NULL')),
        sa.Column('status', sa.Enum('OPEN', 'INVESTIGATING', 'RESOLVED', 'CLOSED', name='incidentstatus'), nullable=False),
        sa.Column('severity', sa.Integer, default=1, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False, index=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('resolved_at', sa.DateTime),
        sa.Column('metadata', postgresql.JSONB),
    )

    # Incident Events table
    op.create_table(
        'incident_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('incident_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sighting_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sightings.id', ondelete='SET NULL')),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('metadata', postgresql.JSONB),
    )

    # Audit Logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource_type', sa.String(50)),
        sa.Column('resource_id', sa.String(255)),
        sa.Column('timestamp', sa.DateTime, nullable=False, index=True),
        sa.Column('ip_address', sa.String(45)),
        sa.Column('user_agent', sa.String(500)),
        sa.Column('details', postgresql.JSONB),
    )

    # Search Queries table
    op.create_table(
        'search_queries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('query_text', sa.Text, nullable=False),
        sa.Column('filters', postgresql.JSONB),
        sa.Column('result_count', sa.Integer),
        sa.Column('created_at', sa.DateTime, nullable=False, index=True),
        sa.Column('execution_time_ms', sa.Float),
    )

    # Add new columns to persons table
    op.add_column('persons', sa.Column('notes', sa.Text))
    op.add_column('persons', sa.Column('photo_urls', postgresql.JSONB))
    op.add_column('persons', sa.Column('is_archived', sa.Boolean, default=False, nullable=False))

    # Add new columns to patterns table
    op.add_column('patterns', sa.Column('pattern_type', sa.String(50)))
    op.add_column('patterns', sa.Column('confidence', sa.Float))
    op.add_column('patterns', sa.Column('detected_at', sa.DateTime))

    # Create indexes
    op.create_index('idx_alerts_created_at', 'alerts', ['created_at'])
    op.create_index('idx_alerts_status', 'alerts', ['status'])
    op.create_index('idx_incidents_created_at', 'incidents', ['created_at'])
    op.create_index('idx_incidents_status', 'incidents', ['status'])
    op.create_index('idx_audit_logs_timestamp', 'audit_logs', ['timestamp'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_audit_logs_timestamp')
    op.drop_index('idx_incidents_status')
    op.drop_index('idx_incidents_created_at')
    op.drop_index('idx_alerts_status')
    op.drop_index('idx_alerts_created_at')

    # Drop new columns from existing tables
    op.drop_column('patterns', 'detected_at')
    op.drop_column('patterns', 'confidence')
    op.drop_column('patterns', 'pattern_type')
    op.drop_column('persons', 'is_archived')
    op.drop_column('persons', 'photo_urls')
    op.drop_column('persons', 'notes')

    # Drop new tables
    op.drop_table('search_queries')
    op.drop_table('audit_logs')
    op.drop_table('incident_events')
    op.drop_table('incidents')
    op.drop_table('alerts')
    op.drop_table('cameras')
    op.drop_table('users')

    # Drop enums
    op.execute('DROP TYPE incidentstatus')
    op.execute('DROP TYPE alertstatus')
    op.execute('DROP TYPE camerastatus')
    op.execute('DROP TYPE userrole')
