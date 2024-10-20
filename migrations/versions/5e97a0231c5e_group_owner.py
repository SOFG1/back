"""group_owner

Revision ID: 5e97a0231c5e
Revises: d6926a070eeb
Create Date: 2024-10-09 15:36:02.996252

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.api.models import ADMIN_ID

# revision identifiers, used by Alembic.
revision: str = "5e97a0231c5e"
down_revision: str | None = "d6926a070eeb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "userownedgrouplink",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["group.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("user_id", "group_id"),
    )
    # All groups are owned by admin for now
    connection = op.get_bind()
    connection.execute(
        sa.text("""
            INSERT INTO userownedgrouplink (user_id, group_id)
            SELECT :user_id, g.id
            FROM "group" g;
            """),
        {"user_id": ADMIN_ID},
    )
    op.add_column("group", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE "group" g
        SET owner_id = uogl.user_id
        FROM userownedgrouplink uogl
        WHERE g.id = uogl.group_id;
        """
    )
    op.alter_column("group", "owner_id", nullable=False)
    op.create_foreign_key("group_owner_id_fkey", "group", "user", ["owner_id"], ["id"])
    op.execute(
        """
        UPDATE "user"
        SET scopes = 'chatbots,conversations,files,groups'
        WHERE scopes = 'chatbots,conversations,files'
        """
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint("group_owner_id_fkey", "group", type_="foreignkey")
    op.drop_column("group", "owner_id")
    op.drop_table("userownedgrouplink")
    # ### end Alembic commands ###
