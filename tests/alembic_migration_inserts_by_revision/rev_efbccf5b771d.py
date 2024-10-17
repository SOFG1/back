from app.api.models import ADMIN_ID, ENTERPRISE_SEARCH_ID

regular_user_uuid = "6720e983-2e91-4daa-9a78-b32ff67a694d"
chatbot_uuid = "9ee0f6c1-f6d0-46dc-8ccf-9838b0520d5b"
conversation_uuid = "2d25b6e7-5ff3-4121-8c93-c8165a5bc525"
dbmessage_uuid = "810e7ac2-eaba-4864-9fc7-26d914ece19e"
file_uuid = "65e9f195-19ee-46a7-b74c-5b08b1c35844"

data = {
    "chatbot": [
        {
            "name": "Enterprise Search",
            "description": "example",
            "system_prompt": "example",
            "citations_mode": True,
            "icon": "example",
            "id": ENTERPRISE_SEARCH_ID,
            "color": "example",
        },
        {
            "name": "example",
            "description": "example",
            "system_prompt": "example",
            "citations_mode": True,
            "icon": "example",
            "id": chatbot_uuid,
            "color": "example",
        },
    ],
    "conversation": {
        "title": "example",
        "id": conversation_uuid,
        "ts_created": "2024-09-07T13:23:11.221527",
        "ts_last_updated": "2024-09-07T13:23:11.221535",
    },
    "dbmessage": {
        "id": dbmessage_uuid,
        "role": "USER",
        "content": "example",
        "llm": "LOCAL",
        "order": 1,
        "citations": {"key": "value"},
    },
    "file": {
        "file_name": "example",
        "creation_time": "2024-09-07T13:23:11.221541",
        "mime_type": "example",
        "file_size": 1,
        "url": "example",
        "indexed": True,
        "id": file_uuid,
        "path": "example",
        "hash": "example",
    },
    "user": [
        {
            "username": "admin2",
            "name": "example",
            "id": ADMIN_ID,
            "password_hash": "example",
            "scopes": "example",
            "creation_time": "2024-09-07T13:23:11.221546",
            "avatar": "example",
        },
        {
            "username": "example",
            "name": "example",
            "id": regular_user_uuid,
            "password_hash": "example",
            "scopes": "example",
            "creation_time": "2024-09-07T13:23:11.221546",
            "avatar": "example",
        },
    ],
    "chatbotconversationlink": {"conversation_id": conversation_uuid, "chatbot_id": chatbot_uuid},
    "chatbotfilelink": {"chatbot_id": chatbot_uuid, "file_id": file_uuid},
    "conversationmessagelink": {"conversation_id": conversation_uuid, "message_id": dbmessage_uuid},
    "userconversationlink": {"user_id": regular_user_uuid, "conversation_id": conversation_uuid},
}
