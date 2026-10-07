"""pilot survey

Revision ID: c3d9a7e1f2b4
Revises: bfe811a535c7
Create Date: 2026-10-06 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d9a7e1f2b4'
down_revision: str | Sequence[str] | None = 'bfe811a535c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pilot_surveys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        sa.Column('experience_years', sa.Float(), nullable=True),
        sa.Column('position', sa.String(length=120), nullable=False),
        sa.Column('self_grade', sa.String(length=20), nullable=True),
        sa.Column('lead_grade', sa.String(length=20), nullable=True),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['assessment_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id'),
    )
    op.create_index(op.f('ix_pilot_surveys_candidate_id'), 'pilot_surveys', ['candidate_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_pilot_surveys_candidate_id'), table_name='pilot_surveys')
    op.drop_table('pilot_surveys')
