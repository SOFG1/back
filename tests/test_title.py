from contextlib import contextmanager
from uuid import UUID

from fastapi import status
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.api.models import (
    ChatbotPublicWithFiles,
    Conversation,
    ConversationPublic,
    DBMessage,
    LLMPublic,
    MessageRole,
)
from app.api.tools.db import db_engine


def test_title(
    test_app: TestClient, test_token: str, test_conversation: ConversationPublic, test_llm: LLMPublic
) -> None:
    # chat with that chatbot in that conversation
    resp = test_app.post(
        f"/api/chat/{test_conversation.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"message": "Hello there", "llm": str(test_llm.id)},
    )

    # create a title for that conversation
    resp = test_app.post(
        f"/api/conversations/{test_conversation.id}/title",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = resp.json()
    assert json
    assert json["title"] == "test title"
    assert json["id"] == str(test_conversation.id)
    assert json["created"] == test_conversation.created.isoformat().replace("+00:00", "Z")
    modified = json["modified"]
    assert json["modified"] > test_conversation.modified.isoformat().replace("+00:00", "Z")

    # patch the title
    resp = test_app.patch(
        f"/api/conversations/{test_conversation.id}/title",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "title": "test title 2",
        },
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json
    assert json["title"] == "test title 2"
    assert json["id"] == str(test_conversation.id)
    assert json["created"] == test_conversation.created.isoformat().replace("+00:00", "Z")
    assert json["modified"] > modified > test_conversation.modified.isoformat().replace("+00:00", "Z")


def test_title_deprecated(
    test_app: TestClient, test_token: str, test_conversation: ConversationPublic, test_llm: LLMPublic
) -> None:
    # chat with that chatbot in that conversation
    resp = test_app.post(
        f"/api/chat/{test_conversation.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"message": "Hello there", "llm": str(test_llm.id)},
    )

    # create a title for that conversation
    resp = test_app.post(
        f"/api/title/{test_conversation.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = resp.json()
    assert json
    assert json["title"] == "test title"
    assert json["id"] == str(test_conversation.id)
    assert json["created"] == test_conversation.created.isoformat().replace("+00:00", "Z")
    modified = json["modified"]
    assert json["modified"] > test_conversation.modified.isoformat().replace("+00:00", "Z")

    # patch the title
    resp = test_app.patch(
        f"/api/title/{test_conversation.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "title": "test title 2",
        },
    )

    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json
    assert json["title"] == "test title 2"
    assert json["id"] == str(test_conversation.id)
    assert json["created"] == test_conversation.created.isoformat().replace("+00:00", "Z")
    assert json["modified"] > modified > test_conversation.modified.isoformat().replace("+00:00", "Z")


def test_create_title_errors(
    test_app: TestClient, test_token: str, test_chatbot: ChatbotPublicWithFiles, test_llm: LLMPublic
) -> None:
    # Attempt to create a title for a non-existing conversation
    resp = test_app.post(
        f"/api/conversations/{uuid7()}/title",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.conversation-not-found", "extra": {}}}

    # Create a new conversation
    resp = test_app.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"chatbot_id": str(test_chatbot.id)},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    conversation_id = resp.json()["id"]

    # Attempt to create a title without a user message (empty history)
    resp = test_app.post(
        f"/api/conversations/{conversation_id}/title",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.no-messages-provided", "extra": {}}}

    # # Attempt to create a title when there is no message from the user
    with contextmanager(db_engine.get_session)() as session:
        conversation: Conversation | None = session.get(Conversation, UUID(conversation_id))
        assert conversation
        ai_message = DBMessage(
            role=MessageRole.AI,
            content="Hello",
            conversation=conversation,
            trace_id="MockID",
            observation_id="MockID",
        )
        session.add(ai_message)
        conversation.history = [ai_message]
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
    resp = test_app.post(
        f"/api/conversations/{conversation.id}/title",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.message-from-user-expected", "extra": {}}}

    # Attempt to create a title when the user is not authorized
    invalid_token = "invalid_token"  # noqa: S105
    resp = test_app.post(
        f"/api/conversations/{conversation_id}/title",
        headers={"Authorization": f"Bearer {invalid_token}"},
        json={"llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.invalid-credentials", "extra": {}}}


def test_create_title_errors_deprecated(
    test_app: TestClient, test_token: str, test_chatbot: ChatbotPublicWithFiles, test_llm: LLMPublic
) -> None:
    # Attempt to create a title for a non-existing conversation
    resp = test_app.post(
        f"/api/title/{uuid7()}", headers={"Authorization": f"Bearer {test_token}"}, json={"llm": str(test_llm.id)}
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.conversation-not-found", "extra": {}}}

    # Create a new conversation
    resp = test_app.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"chatbot_id": str(test_chatbot.id)},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    conversation_id = resp.json()["id"]

    # Attempt to create a title without a user message (empty history)
    resp = test_app.post(
        f"/api/title/{conversation_id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.no-messages-provided", "extra": {}}}

    # # Attempt to create a title when there is no message from the user
    with contextmanager(db_engine.get_session)() as session:
        conversation: Conversation | None = session.get(Conversation, UUID(conversation_id))
        assert conversation
        ai_message = DBMessage(
            role=MessageRole.AI,
            content="Hello",
            conversation=conversation,
            trace_id="MockID",
            observation_id="MockID",
        )
        session.add(ai_message)
        conversation.history = [ai_message]
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
    resp = test_app.post(
        f"/api/title/{conversation.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.message-from-user-expected", "extra": {}}}

    # Attempt to create a title when the user is not authorized
    invalid_token = "invalid_token"  # noqa: S105
    resp = test_app.post(
        f"/api/title/{conversation_id}",
        headers={"Authorization": f"Bearer {invalid_token}"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.invalid-credentials", "extra": {}}}


def test_patch_title_errors(test_app: TestClient, test_token: str, test_conversation: ConversationPublic) -> None:
    # Attempt to patch a title for a non-existing conversation
    resp = test_app.patch(
        f"/api/conversations/{uuid7()}/title",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"title": "New Title"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.conversation-not-found", "extra": {}}}

    # Attempt to patch the title when the user is not authorized
    invalid_token = "invalid_token"  # noqa: S105
    resp = test_app.patch(
        f"/api/conversations/{test_conversation.id}/title",
        headers={"Authorization": f"Bearer {invalid_token}"},
        json={"title": "New Title"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.invalid-credentials", "extra": {}}}

    # Attempt to patch the title with an invalid title (empty string)
    resp = test_app.patch(
        f"/api/conversations/{test_conversation.id}/title",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "title": "",  # Invalid title
        },
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.json()
    assert resp.json()["detail"]["extra"]["errors"][0]["msg"] == "String should have at least 1 character"


def test_patch_title_errors_deprecated(
    test_app: TestClient, test_token: str, test_conversation: ConversationPublic
) -> None:
    # Attempt to patch a title for a non-existing conversation
    resp = test_app.patch(
        f"/api/title/{uuid7()}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"title": "New Title"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.conversation-not-found", "extra": {}}}

    # Attempt to patch the title when the user is not authorized
    invalid_token = "invalid_token"  # noqa: S105
    resp = test_app.patch(
        f"/api/title/{test_conversation.id}",
        headers={"Authorization": f"Bearer {invalid_token}"},
        json={"title": "New Title"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.invalid-credentials", "extra": {}}}

    # Attempt to patch the title with an invalid title (empty string)
    resp = test_app.patch(
        f"/api/title/{test_conversation.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "title": "",  # Invalid title
        },
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.json()
    assert resp.json()["detail"]["extra"]["errors"][0]["msg"] == "String should have at least 1 character"
