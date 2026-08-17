"""add_cardio_logs

Revision ID: a1b2c3d4e5f6
Revises: e1b6ab03639a
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e1b6ab03639a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cardio_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("cardio_type", sa.String(length=50), nullable=False),
        sa.Column("performed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("calories_burned", sa.Integer(), nullable=True),
        sa.Column("distance_km", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("avg_heart_rate", sa.Integer(), nullable=True),
        sa.Column("intensity", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["workout_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cardio_logs_user_id", "cardio_logs", ["user_id"])
    op.create_index("ix_cardio_logs_session_id", "cardio_logs", ["session_id"])
    op.create_index("ix_cardio_logs_log_date", "cardio_logs", ["log_date"])


def downgrade() -> None:
    op.drop_index("ix_cardio_logs_log_date", table_name="cardio_logs")
    op.drop_index("ix_cardio_logs_session_id", table_name="cardio_logs")
    op.drop_index("ix_cardio_logs_user_id", table_name="cardio_logs")
    op.drop_table("cardio_logs")
