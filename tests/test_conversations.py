from contextlib import contextmanager

from fastapi import status
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.api.models import Chatbot, ChatbotPublicWithFiles, ConversationPublic, UserPublic
from app.api.tools.db import db_engine


def test_conversations(
    test_app: TestClient, test_token: str, test_chatbot: ChatbotPublicWithFiles, test_conversation: ConversationPublic
) -> None:
    # create a conversation with that chatbot
    resp = test_app.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"chatbot_id": str(test_chatbot.id)},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = conversation_object = resp.json()
    conversation_id = json["id"]
    assert json
    assert json["title"] is None

    # get all conversations
    resp = test_app.get(
        "/api/conversations",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    expected = sorted(
        [test_conversation.model_dump(mode="json"), conversation_object], key=lambda x: x["modified"], reverse=True
    )
    actual = resp.json()
    assert len(actual) == len(expected)
    expected[0]["modified"] = actual[0]["modified"]
    assert actual == expected

    # get a conversation
    resp = test_app.get(
        f"/api/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {
        "title": conversation_object["title"],
        "id": conversation_id,
        "created": conversation_object["created"],
        "modified": conversation_object["modified"],
        "history": [],
        "chatbot": test_chatbot.model_dump(mode="json", exclude={"files"}),
    }

    # delete a conversation
    resp = test_app.delete(
        f"/api/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {
        "ok": True,
        "message": f"Deleted conversation {conversation_id}",
    }


def test_create_conversation_chatbot_not_found(test_app: TestClient, test_token: str) -> None:
    # Attempting to create a conversation with a non-existing chatbot id
    resp = test_app.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"chatbot_id": str(uuid7())},  # Invalid ID
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.chatbot-not-found", "extra": {}}}


def test_get_single_conversation_not_found(test_app: TestClient, test_token: str) -> None:
    # Attempting to get a conversation with a non-existing id
    resp = test_app.get(
        f"/api/conversations/{uuid7()}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.conversation-not-found", "extra": {}}}


def test_delete_conversation_not_found(test_app: TestClient, test_token: str) -> None:
    # Attempting to delete a conversation with a non-existing id
    resp = test_app.delete(
        f"/api/conversations/{uuid7()}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.conversation-not-found", "extra": {}}}


def test_get_single_conversation_unauthorized(test_app: TestClient, test_conversation: ConversationPublic) -> None:
    # Simulate an unauthorized user trying to access the conversation
    unauthorized_token = "another-user-token"  # noqa: S105
    resp = test_app.get(
        f"/api/conversations/{test_conversation.id}",
        headers={"Authorization": f"Bearer {unauthorized_token}"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.invalid-credentials", "extra": {}}}


def test_delete_conversation_unauthorized(test_app: TestClient, test_conversation: ConversationPublic) -> None:
    # Simulate an unauthorized user trying to delete the conversation
    unauthorized_token = "another-user-token"  # noqa: S105
    resp = test_app.delete(
        f"/api/conversations/{test_conversation.id}",
        headers={"Authorization": f"Bearer {unauthorized_token}"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.invalid-credentials", "extra": {}}}


def test_conversation_on_deleted_chatbot(
    test_app: TestClient, test_token: str, test_chatbot: ChatbotPublicWithFiles, test_conversation: ConversationPublic
) -> None:
    # Soft-delete the chatbot
    resp = test_app.delete(
        f"/api/chatbots/{test_chatbot.id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # Get conversation linked to the deleted chatbot
    resp = test_app.get(
        f"/api/conversations/{test_conversation.id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # Ensure chatbot info is still available in the conversation
    assert resp.json()["chatbot"]["id"] == str(test_chatbot.id)
    assert resp.json()["chatbot"]["deleted"] is not None


def test_delete_deleted_chatbot_after_last_conversation(
    test_app: TestClient, test_token: str, test_chatbot: ChatbotPublicWithFiles, test_conversation: ConversationPublic
) -> None:
    # Add another conversation with chatbot:
    resp = test_app.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"chatbot_id": str(test_chatbot.id)},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    conversation2_id = resp.json()["id"]

    # Soft-delete the chatbot
    resp = test_app.delete(
        f"/api/chatbots/{test_chatbot.id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # Get conversation linked to the deleted chatbot
    resp = test_app.get(
        f"/api/conversations/{test_conversation.id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # Ensure chatbot info is still available in the conversation
    assert resp.json()["chatbot"]["id"] == str(test_chatbot.id)
    assert resp.json()["chatbot"]["deleted"] is not None

    # Delete first conversation
    resp = test_app.delete(
        f"/api/conversations/{test_conversation.id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # Get second conversation linked to the deleted chatbot
    resp = test_app.get(
        f"/api/conversations/{conversation2_id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # Ensure chatbot info is still available in the conversation
    assert resp.json()["chatbot"]["id"] == str(test_chatbot.id)
    assert resp.json()["chatbot"]["deleted"] is not None

    # Delete second conversation
    resp = test_app.delete(
        f"/api/conversations/{conversation2_id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # Ensure chatbot is now deleted
    with contextmanager(db_engine.get_session)() as session:
        chatbot: Chatbot | None = session.get(Chatbot, test_chatbot.id)
        assert chatbot is None


def test_conversation_on_deleted_shared_chatbot(
    test_app: TestClient,
    test_token: str,
    fake_user: UserPublic,
    test_fake_token: str,
    test_chatbot: ChatbotPublicWithFiles,
) -> None:
    # Share the chatbot with another user
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot.id}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # Create a conversation with that user
    resp = test_app.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={"chatbot_id": str(test_chatbot.id)},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    conversation_id = resp.json()["id"]

    # Soft-delete the chatbot
    resp = test_app.delete(
        f"/api/chatbots/{test_chatbot.id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # Try to access the conversation linked to the deleted chatbot with the other user
    resp = test_app.get(
        f"/api/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # Ensure chatbot info is still available for the other user
    assert resp.json()["chatbot"]["id"] == str(test_chatbot.id)
    assert resp.json()["chatbot"]["deleted"] is not None
