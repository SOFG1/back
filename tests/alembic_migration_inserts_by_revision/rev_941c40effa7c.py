from app.api.models import ADMIN_ID

regular_user_uuid = "6720e983-2e91-4daa-9a78-b32ff67a694d"
chatbot_uuid = "9ee0f6c1-f6d0-46dc-8ccf-9838b0520d5b"
conversation_uuid = "2d25b6e7-5ff3-4121-8c93-c8165a5bc525"
dbmessage_uuid = "810e7ac2-eaba-4864-9fc7-26d914ece19e"
file_uuid = "65e9f195-19ee-46a7-b74c-5b08b1c35844"

group_uuid = "03481de3-a5dd-4c72-9fc5-7f8e98c7f91a"
fileuser_uuid = "56d29833-0b71-4670-8970-a8fa152902ef"

data = {
    "group": {
        "name": "example",
        "description": "example",
        "icon": "example",
        "id": group_uuid,
        "creation_time": "2024-09-07T13:42:55.413992",
    },
    "fileuser": {
        "id": fileuser_uuid,
        "creation_time": "2024-09-07T13:42:55.414002",
        "modification_time": "2024-09-07T13:42:55.414004",
        "owner_id": regular_user_uuid,
        "file_name": "example",
        "directory": "example",
    },
    "usergrouplink": {"user_id": regular_user_uuid, "group_id": group_uuid},
    "filefileuserlink": {"file_user_id": fileuser_uuid, "file_id": file_uuid},
    "chatbotfileuserlink": {"chatbot_id": chatbot_uuid, "file_user_id": fileuser_uuid},
    "groupchatbotlink": {"group_id": group_uuid, "chatbot_id": chatbot_uuid},
    "userchatbotlink": {"user_id": regular_user_uuid, "chatbot_id": chatbot_uuid},
    "userfilelink": {"user_id": regular_user_uuid, "file_user_id": fileuser_uuid},
    "usersharedlink": {"user_id": regular_user_uuid, "chatbot_id": chatbot_uuid},
}

delete = {
    "userchatbotlink": {"user_id": ADMIN_ID, "chatbot_id": chatbot_uuid},
}
