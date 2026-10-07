"""claimed (not confirmed) grade

Revision ID: d4e8b2c6a1f3
Revises: c3d9a7e1f2b4
Create Date: 2026-10-07 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e8b2c6a1f3'
down_revision: str | Sequence[str] | None = 'c3d9a7e1f2b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('candidates', sa.Column('claimed_grade', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('candidates', 'claimed_grade')
