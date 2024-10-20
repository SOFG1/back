"""one_to_many_constraints

Revision ID: 02658dbf370a
Revises: a103508c014d
Create Date: 2024-10-15 15:07:02.111744

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "02658dbf370a"
down_revision: str | None = "a103508c014d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_unique_constraint(
        "chatbotconversationlink_conversation_id_key", "chatbotconversationlink", ["conversation_id"]
    )
    op.create_unique_constraint("conversationmessagelink_message_id_key", "conversationmessagelink", ["message_id"])
    op.create_unique_constraint("filefileuserlink_file_user_id_key", "filefileuserlink", ["file_user_id"])
    op.create_unique_constraint("userchatbotlink_chatbot_id_key", "userchatbotlink", ["chatbot_id"])
    op.create_unique_constraint("userconversationlink_conversation_id_key", "userconversationlink", ["conversation_id"])
    op.create_unique_constraint("userfilelink_file_user_id_key", "userfilelink", ["file_user_id"])
    op.create_unique_constraint("userownedgrouplink_group_id_key", "userownedgrouplink", ["group_id"])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint("userownedgrouplink_group_id_key", "userownedgrouplink", type_="unique")
    op.drop_constraint("userfilelink_file_user_id_key", "userfilelink", type_="unique")
    op.drop_constraint("userconversationlink_conversation_id_key", "userconversationlink", type_="unique")
    op.drop_constraint("userchatbotlink_chatbot_id_key", "userchatbotlink", type_="unique")
    op.drop_constraint("filefileuserlink_file_user_id_key", "filefileuserlink", type_="unique")
    op.drop_constraint("conversationmessagelink_message_id_key", "conversationmessagelink", type_="unique")
    op.drop_constraint("chatbotconversationlink_conversation_id_key", "chatbotconversationlink", type_="unique")
    # ### end Alembic commands ###
