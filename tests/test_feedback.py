from fastapi import status
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.api.models import ConversationPublic, FeedbackOptions, LLMPublic, MessageRole


def test_feedback(
    test_app: TestClient, test_token: str, test_conversation: ConversationPublic, test_llm: LLMPublic
) -> None:
    # chat with that chatbot in that conversation
    resp = test_app.post(
        f"/api/chat/{test_conversation.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"message": "Hello there", "llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # get conversation for history
    resp = test_app.get(f"/api/conversations/{test_conversation.id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    ai_message = resp.json()["history"][1]
    assert ai_message["role"] == MessageRole.AI
    assert ai_message["feedback_value"] is None
    message_id = ai_message["id"]

    # add feedback to AI answer
    resp = test_app.post(
        f"/api/conversations/{test_conversation.id}/feedback/{message_id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"comment": "Just a test_feedback", "value": 1, "name": FeedbackOptions.not_helpful},
    )

    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {"ok": True, "message": "Thank you for your feedback."}

    # get conversation for history
    resp = test_app.get(f"/api/conversations/{test_conversation.id}", headers={"Authorization": f"Bearer {test_token}"})

    assert resp.status_code == status.HTTP_200_OK, resp.json()
    ai_message = resp.json()["history"][1]
    assert ai_message["role"] == MessageRole.AI
    assert ai_message["feedback_value"] == 1


def test_feedback_no_message(test_app: TestClient, test_conversation: ConversationPublic, test_token: str) -> None:
    message_id = uuid7()
    resp = test_app.post(
        f"/api/conversations/{test_conversation.id}/feedback/{message_id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"comment": "Just a test_feedback", "value": 1},
    )

    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.message-not-found", "extra": {}}}


def test_feedback_not_ai(
    test_app: TestClient, test_token: str, test_conversation: ConversationPublic, test_llm: LLMPublic
) -> None:
    # chat with that chatbot in that conversation
    resp = test_app.post(
        f"/api/chat/{test_conversation.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"message": "Hello there", "llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # get conversation for history
    resp = test_app.get(f"/api/conversations/{test_conversation.id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    user_message = resp.json()["history"][0]
    assert user_message["role"] == MessageRole.USER
    message_id = user_message["id"]

    resp = test_app.post(
        f"/api/conversations/{test_conversation.id}/feedback/{message_id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"comment": "Just a test_feedback", "value": 1, "name": FeedbackOptions.not_helpful},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.rate-only-ai-messages", "extra": {}}}


def test_feedback_not_owner(
    test_app: TestClient,
    test_token: str,
    test_fake_token: str,
    test_conversation: ConversationPublic,
    test_llm: LLMPublic,
) -> None:
    # chat with that chatbot in that conversation
    resp = test_app.post(
        f"/api/chat/{test_conversation.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"message": "Hello there", "llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # get conversation for history
    resp = test_app.get(f"/api/conversations/{test_conversation.id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    message_id = resp.json()["history"][1]["id"]

    resp = test_app.post(
        f"/api/conversations/{test_conversation.id}/feedback/{message_id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={"comment": "Just a test_feedback", "value": 1},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.not-authorized", "extra": {}}}
