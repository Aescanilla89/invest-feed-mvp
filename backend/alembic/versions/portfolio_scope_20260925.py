"""Add scope to distinguish current portfolio from legacy positions.

Revision ID: portfolio_scope_20260925
Revises: 6ab752a2f0ca
"""

from alembic import op
import sqlalchemy as sa


revision = "portfolio_scope_20260925"
down_revision = "6ab752a2f0ca"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "portfolio_positions",
        sa.Column(
            "portfolio_scope",
            sa.String(length=16),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.execute(
        """
        UPDATE portfolio_positions
        SET portfolio_scope = CASE
            WHEN status = 'open' AND method <> 'featured' THEN 'legacy'
            ELSE 'current'
        END
        """
    )


def downgrade() -> None:
    op.drop_column("portfolio_positions", "portfolio_scope")
