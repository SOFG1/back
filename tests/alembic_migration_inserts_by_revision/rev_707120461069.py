from tests.alembic_migration_inserts_by_revision.rev_efbccf5b771d import chatbot_uuid, regular_user_uuid

conversation_long_title_id = "0192629d-b067-76de-94ba-e5857fca31a0"
conversation_null_title_id = "019262a1-1bc3-7a19-a48f-34fc8d07f77b"

data = {
    "conversation": [
        {
            "title": "Example title that is longer than 120 characters, indeed this title is more than 200 characters long. Don't believe me? Then check, go ahead, I will wait. Are you satisfied now? Good. And don't question me again.",
            "id": conversation_long_title_id,
        },
        {
            "title": None,
            "id": conversation_null_title_id,
        },
    ],
    "chatbotconversationlink": [
        {"conversation_id": conversation_long_title_id, "chatbot_id": chatbot_uuid},
        {"conversation_id": conversation_null_title_id, "chatbot_id": chatbot_uuid},
    ],
    "userconversationlink": [
        {"user_id": regular_user_uuid, "conversation_id": conversation_long_title_id},
        {"user_id": regular_user_uuid, "conversation_id": conversation_null_title_id},
    ],
}
