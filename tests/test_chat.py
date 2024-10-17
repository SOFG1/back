from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session
from uuid6 import uuid7

from app.api.models import ConversationPublic, DBMessage, LLMPublic


def test_chat(
    test_app: TestClient, test_token: str, test_conversation: ConversationPublic, test_llm: LLMPublic
) -> None:
    resp = test_app.post(
        f"/api/chat/{test_conversation.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"message": "Hello there", "llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    result = resp.read()
    assert b'data: "test"\n\ndata: " test.pdf"\n\nevent: context\ndata: {"citations": []}\n\n' in result
    assert b"event: metadata\n" in result
    assert all(x in result for x in (b"trace_id", b"message_id", b"observation_id"))


# For this test, we need to somehow see if the expired file get quoted or not
def test_chat_expired_file(
    test_app: TestClient, test_token: str, test_conversation_expired_file: ConversationPublic, test_llm: LLMPublic
) -> None:
    resp = test_app.post(
        f"/api/chat/{test_conversation_expired_file.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"message": "Hello there", "llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    result = resp.read()
    assert b'data: "test"\n\ndata: " test.pdf"\n\nevent: context\ndata: {"citations": []}\n\n' in result
    assert b"event: metadata\n" in result
    assert all(x in result for x in (b"trace_id", b"message_id", b"observation_id"))


def test_chat_conversation_not_found(test_app: TestClient, test_token: str, test_llm: LLMPublic) -> None:
    resp = test_app.post(
        f"/api/chat/{uuid7()}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"message": "Hello there", "llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.conversation-not-found", "extra": {}}}


def test_chat_unauthorized(
    test_app: TestClient, test_user_token: str, test_conversation: ConversationPublic, test_llm: LLMPublic
) -> None:
    resp = test_app.post(
        f"/api/chat/{test_conversation.id}",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={"message": "Hello there", "llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.not-authorized", "extra": {}}}


def test_patch_chat_conversation_not_found(test_app: TestClient, test_token: str, test_llm: LLMPublic) -> None:
    conversation_id = uuid7()
    message_id = uuid7()

    resp = test_app.patch(
        f"/api/chat/{conversation_id}/{message_id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"message": "Updated message", "llm": str(test_llm.id)},
    )

    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.conversation-not-found", "extra": {}}}


def test_patch_chat_message_not_found(
    test_app: TestClient, test_token: str, test_conversation: ConversationPublic, test_llm: LLMPublic
) -> None:
    message_id = uuid7()

    resp = test_app.patch(
        f"/api/chat/{test_conversation.id}/{message_id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"message": "Updated message", "llm": str(test_llm.id)},
    )

    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.message-not-found", "extra": {}}}


def test_patch_chat_message_not_last(
    test_app: TestClient,
    test_token: str,
    test_conversation: ConversationPublic,
    test_llm: LLMPublic,
    create_messages: tuple[DBMessage, DBMessage],
) -> None:
    resp = test_app.patch(
        f"/api/chat/{test_conversation.id}/{create_messages[0].id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"message": "Updated message", "llm": str(test_llm.id)},
    )

    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.json()
    assert resp.json() == {
        "detail": {"error_code": "backend.error.not-the-last-message-was-chosen-for-editing", "extra": {}}
    }


def test_patch_chat_message(
    test_app: TestClient,
    test_token: str,
    test_conversation: ConversationPublic,
    test_llm: LLMPublic,
    create_messages: tuple[DBMessage, DBMessage],
    db_session: Session,
) -> None:
    resp = test_app.patch(
        f"/api/chat/{test_conversation.id}/{create_messages[1].id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"message": "Updated message", "llm": str(test_llm.id)},
    )
    db_session.commit()
    assert resp.status_code == status.HTTP_200_OK
    result = resp.read()
    assert b'data: "test"\n\ndata: " test.pdf"\n\nevent: context\ndata: {"citations": []}\n\n' in result
    assert b"event: metadata\n" in result
    assert all(x in result for x in (b"trace_id", b"message_id", b"observation_id"))
    assert create_messages[1].content == "Updated message"
