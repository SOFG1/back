"""add AdminSettings table

Revision ID: 20618054f0a3
Revises: ce35174dd5fa
Create Date: 2024-09-07 15:07:08.089201

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlmodel.sql.sqltypes import AutoString

# revision identifiers, used by Alembic.
revision: str = "20618054f0a3"
down_revision: str | None = "ce35174dd5fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "adminsetting",
        sa.Column("key", AutoString(), nullable=False),
        sa.Column("value", AutoString(), nullable=False),
        sa.Column("modified", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("adminsetting")
    # ### end Alembic commands ###
