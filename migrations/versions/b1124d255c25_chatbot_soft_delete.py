"""chatbot_soft_delete

Revision ID: b1124d255c25
Revises: ce71d72138c7
Create Date: 2024-10-01 22:56:24.269947

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1124d255c25"
down_revision: str | None = "ce71d72138c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("chatbot", sa.Column("deleted", sa.DateTime(timezone=True), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("chatbot", "deleted")
    # ### end Alembic commands ###
