"""Add FileBase.pdf_path and add uniqueness constraint.

Revision ID: e31e7a1e2d53
Revises: cb7fd7380dc3
Create Date: 2024-09-26 13:56:10.483759

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlmodel.sql.sqltypes import AutoString

# revision identifiers, used by Alembic.
revision: str = "e31e7a1e2d53"
down_revision: str | None = "cb7fd7380dc3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("file", sa.Column("pdf_path", AutoString(), nullable=True))
    op.drop_index("ix_file_path", table_name="file")
    op.create_index(op.f("ix_file_path"), "file", ["path"], unique=True)
    op.create_index(op.f("ix_file_pdf_path"), "file", ["pdf_path"], unique=False)
    op.create_unique_constraint("path_with_pdf_path_unique", "file", ["path", "pdf_path"])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint("path_with_pdf_path_unique", "file", type_="unique")
    op.drop_index(op.f("ix_file_pdf_path"), table_name="file")
    op.drop_index(op.f("ix_file_path"), table_name="file")
    op.create_index("ix_file_path", "file", ["path"], unique=False)
    op.drop_column("file", "pdf_path")
    # ### end Alembic commands ###
