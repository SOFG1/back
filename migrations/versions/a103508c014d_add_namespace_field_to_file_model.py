"""add namespace field to file model

Revision ID: a103508c014d
Revises: 643689bde6e7
Create Date: 2024-10-04 00:54:51.874781

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlmodel.sql.sqltypes import AutoString

# revision identifiers, used by Alembic.
revision: str = "a103508c014d"
down_revision: str | None = "643689bde6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("file", sa.Column("namespace", AutoString(length=256), nullable=True))
    op.create_index(op.f("ix_file_namespace"), "file", ["namespace"], unique=False)
    op.execute("UPDATE file SET namespace = 'Default_index_openai_text_embedding_3_small' WHERE namespace IS NULL")
    op.alter_column("file", "namespace", nullable=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_index(op.f("ix_file_namespace"), table_name="file")
    op.drop_column("file", "namespace")
    # ### end Alembic commands ###
