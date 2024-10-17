"""user feedback

Revision ID: ce35174dd5fa
Revises: fc0cb08a4a51
Create Date: 2024-09-03 15:08:07.700388

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlmodel.sql.sqltypes import AutoString

# revision identifiers, used by Alembic.
revision: str = "ce35174dd5fa"
down_revision: str | None = "fc0cb08a4a51"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("dbmessage", sa.Column("trace_id", AutoString(), nullable=True))
    op.add_column("dbmessage", sa.Column("observation_id", AutoString(), nullable=True))
    op.add_column("dbmessage", sa.Column("feedback_value", sa.Float(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("dbmessage", "feedback_value")
    op.drop_column("dbmessage", "observation_id")
    op.drop_column("dbmessage", "trace_id")
    # ### end Alembic commands ###
