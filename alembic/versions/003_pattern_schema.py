"""Align analytics pattern persistence with the application model."""

from alembic import op
import sqlalchemy as sa

revision = "003_pattern_schema"
down_revision = "002_extended_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("patterns", "person_id", existing_type=sa.String(length=36), nullable=True)


def downgrade() -> None:
    op.alter_column("patterns", "person_id", existing_type=sa.String(length=36), nullable=False)
