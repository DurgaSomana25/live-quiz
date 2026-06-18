"""add question_served_at to quiz_sessions

Revision ID: c1a82a7039ff
Revises: 
Create Date: 2026-06-17 16:32:26.884596

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a82a7039ff'
down_revision: Union[str, None] = 'f46b17a2de1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('quiz_sessions', sa.Column('question_served_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('quiz_sessions', 'question_served_at')
