"""add analysis_failure_logs

Revision ID: 5d547a63f0e6
Revises: ecb69044639d
Create Date: 2026-08-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d547a63f0e6'
down_revision: Union[str, Sequence[str], None] = 'ecb69044639d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('analysis_failure_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('listing_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('failure_type', sa.String(length=120), nullable=False),
    sa.Column('cause_type', sa.String(length=120), nullable=False),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analysis_failure_logs_listing_id'), 'analysis_failure_logs', ['listing_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_analysis_failure_logs_listing_id'), table_name='analysis_failure_logs')
    op.drop_table('analysis_failure_logs')
