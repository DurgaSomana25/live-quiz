"""synchronized quiz clock

Revision ID: a3f91b2c0e44
Revises: c1a82a7039ff
Create Date: 2026-06-18 10:00:00.000000

Changes:
  quizzes        + started_at (DateTime, nullable)
  quizzes        + quiz_status (String, default 'pending')
  quiz_sessions  - question_served_at (replaced by global clock)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a3f91b2c0e44'
down_revision: Union[str, None] = 'c1a82a7039ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('quizzes', sa.Column('started_at', sa.DateTime(), nullable=True))
    op.add_column('quizzes', sa.Column('quiz_status', sa.String(), nullable=False, server_default='pending'))
    op.drop_column('quiz_sessions', 'question_served_at')


def downgrade() -> None:
    op.add_column('quiz_sessions', sa.Column('question_served_at', sa.DateTime(), nullable=True))
    op.drop_column('quizzes', 'quiz_status')
    op.drop_column('quizzes', 'started_at')
