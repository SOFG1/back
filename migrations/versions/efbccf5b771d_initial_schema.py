"""Initial Schema

Revision ID: efbccf5b771d
Revises:
Create Date: 2024-08-12 16:42:48.062200

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlmodel.sql.sqltypes import AutoString

# revision identifiers, used by Alembic.
revision: str = "efbccf5b771d"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "chatbot",
        sa.Column("name", AutoString(length=100), nullable=False),
        sa.Column("description", AutoString(length=1000), nullable=False),
        sa.Column("system_prompt", AutoString(length=2500), nullable=False),
        sa.Column("citations_mode", sa.Boolean(), nullable=False),
        sa.Column("icon", AutoString(length=25), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("color", AutoString(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "conversation",
        sa.Column("title", AutoString(length=300), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ts_created", sa.DateTime(), nullable=False),
        sa.Column("ts_last_updated", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "dbmessage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Enum("USER", "AI", name="messagerole"), nullable=False),
        sa.Column("content", AutoString(), nullable=False),
        sa.Column("llm", sa.Enum("LOCAL", "OPENAI", name="llmoptions"), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "file",
        sa.Column("file_name", AutoString(), nullable=False),
        sa.Column("creation_time", sa.DateTime(), nullable=False),
        sa.Column("mime_type", AutoString(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("url", AutoString(), nullable=False),
        sa.Column("indexed", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("path", AutoString(), nullable=False),
        sa.Column("hash", AutoString(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_file_hash"), "file", ["hash"], unique=True)
    op.create_index(op.f("ix_file_path"), "file", ["path"], unique=False)
    op.create_table(
        "user",
        sa.Column("username", AutoString(length=100), nullable=False),
        sa.Column("name", AutoString(length=100), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("password_hash", AutoString(), nullable=False),
        sa.Column("scopes", AutoString(), nullable=False),
        sa.Column("creation_time", sa.DateTime(), nullable=False),
        sa.Column("avatar", AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_username"), "user", ["username"], unique=True)
    op.create_table(
        "chatbotconversationlink",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("chatbot_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["chatbot_id"], ["chatbot.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"]),
        sa.PrimaryKeyConstraint("conversation_id", "chatbot_id"),
    )
    op.create_table(
        "chatbotfilelink",
        sa.Column("chatbot_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["chatbot_id"], ["chatbot.id"]),
        sa.ForeignKeyConstraint(["file_id"], ["file.id"]),
        sa.PrimaryKeyConstraint("chatbot_id", "file_id"),
    )
    op.create_table(
        "conversationmessagelink",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"]),
        sa.ForeignKeyConstraint(["message_id"], ["dbmessage.id"]),
        sa.PrimaryKeyConstraint("conversation_id", "message_id"),
    )
    op.create_table(
        "userconversationlink",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("user_id", "conversation_id"),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("userconversationlink")
    op.drop_table("conversationmessagelink")
    op.drop_table("chatbotfilelink")
    op.drop_table("chatbotconversationlink")
    op.drop_index(op.f("ix_user_username"), table_name="user")
    op.drop_table("user")
    op.drop_index(op.f("ix_file_path"), table_name="file")
    op.drop_index(op.f("ix_file_hash"), table_name="file")
    op.drop_table("file")
    op.drop_table("dbmessage")
    op.drop_table("conversation")
    op.drop_table("chatbot")
    # ### end Alembic commands ###
