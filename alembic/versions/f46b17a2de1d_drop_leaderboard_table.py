"""drop leaderboard table

Revision ID: f46b17a2de1d
Revises:
Create Date: 2026-06-17 00:00:00.000000

Already applied directly on DB. Stub kept so Alembic chain is intact.
"""
from typing import Sequence, Union

revision: str = 'f46b17a2de1d'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass  # already applied


def downgrade() -> None:
    pass
