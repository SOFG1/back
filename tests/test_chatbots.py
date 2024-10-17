import pytest
from fastapi import status
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.api.models import LLM, ChatbotId, ChatbotPublic, ChatbotPublicWithFiles, FilePublic, User, UserPublic
from tests.conftest import GroupFactory


def test_chatbots_not_authorized(
    test_app: TestClient,
    test_fake_token: str,
    test_file: FilePublic,
    test_chatbot: ChatbotPublicWithFiles,
) -> None:
    # get a chatbot - not authorized
    resp = test_app.get(
        f"/api/chatbots/{test_chatbot.model_dump()['id']}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    # add files to a chatbot - not authorized
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot.model_dump()['id']}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json=[str(test_file.id)],
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    # change a chatbot - not authorized
    resp = test_app.patch(
        f"/api/chatbots/{test_chatbot.model_dump()['id']}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={
            "name": "test_chatbot2",
            "description": "description2",
            "color": "yellow",
            "icon": "other",
            "system_prompt": "system_prompt2",
            "citations_mode": True,
            "files": [],
        },
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    # delete a chatbot - not authorized
    resp = test_app.delete(
        f"/api/chatbots/{test_chatbot.model_dump()['id']}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    # Get all chatbots
    resp = test_app.get("/api/chatbots", headers={"Authorization": f"Bearer {test_fake_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json == []


def test_chatbots(test_app: TestClient, test_token: str, test_file: FilePublic) -> None:
    # create a chatbot without files
    resp = test_app.post(
        "/api/chatbots",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "name": "test_chatbot",
            "description": "description",
            "system_prompt": "system_prompt",
            "citations_mode": False,
            "color": "green",
            "icon": "default",
            "files": [],
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = chatbot_object = resp.json()
    assert json
    assert json["name"] == "test_chatbot"
    assert json["description"] == "description"
    assert json["system_prompt"] == "system_prompt"
    assert not json["citations_mode"]
    assert json["color"] == "green"
    assert json["icon"] == "default"
    assert json["files"] == []

    # create a chatbot with same name and same user
    resp = test_app.post(
        "/api/chatbots",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "name": "test_chatbot",
            "description": "description",
            "system_prompt": "system_prompt",
            "citations_mode": False,
            "color": "green",
            "icon": "default",
            "files": [],
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    chatbot_object2 = resp.json()
    assert chatbot_object2["id"] != chatbot_object["id"]

    # create a chatbot with same name (like test_chatbot), but different user
    # TODO: this should be using a different user!
    # resp = test_app.post(
    #     "/api/chatbots",
    #     headers={"Authorization": f"Bearer {test_token2}"},
    #     json={
    #         "name": "test_chatbot",
    #         "description": "description",
    #         "system_prompt": "system_prompt",
    #         "citations_mode": False,
    #         "color": "yellow",
    #         "icon": "default",
    #         "files": [],
    #     },
    # )
    # assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    # json = chatbot_object1 = resp.json()
    # assert json
    # assert json["name"] == "test_chatbot_fixture"
    # assert json["description"] == "description"
    # assert json["system_prompt"] == "system_prompt"
    # assert not json["citations_mode"]
    # assert json["color"] == "yellow"
    # assert json["icon"] == "default"
    # assert json["files"] == []

    # create a chatbot with files
    resp = test_app.post(
        "/api/chatbots",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "name": "test_chatbot_files",
            "description": "description",
            "system_prompt": "system_prompt",
            "citations_mode": False,
            "color": "red",
            "icon": "default",
            "files": [str(test_file.id)],
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = resp.json()
    assert json
    assert json["name"] == "test_chatbot_files"
    assert json["color"] == "red"
    assert json["icon"] == "default"
    assert json["files"]
    chatbot_object3 = json

    # get a chatbot
    resp = test_app.get(
        f"/api/chatbots/{chatbot_object['id']}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == chatbot_object

    # add files to a chatbot
    resp = test_app.post(
        f"/api/chatbots/{chatbot_object['id']}",
        headers={"Authorization": f"Bearer {test_token}"},
        json=[str(test_file.id)],
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    chatbot_object["files"] = [test_file.model_dump(mode="json")]

    # change a chatbot
    resp = test_app.patch(
        f"/api/chatbots/{chatbot_object['id']}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "name": "test_chatbot2",
            "description": "description2",
            "color": "blue",
            "icon": "other",
            "system_prompt": "system_prompt2",
            "citations_mode": True,
            "files": [],
        },
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json
    assert json["name"] == "test_chatbot2"
    assert json["description"] == "description2"
    assert json["color"] == "blue"
    assert json["icon"] == "other"
    assert json["system_prompt"] == "system_prompt2"
    assert json["citations_mode"]
    assert json["files"] == []

    # set files with patch
    resp = test_app.patch(
        f"/api/chatbots/{chatbot_object['id']}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "files": [str(test_file.id)],
        },
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    chatbot_object["files"] = [test_file.model_dump(mode="json")]

    # delete a chatbot
    resp = test_app.delete(
        f"/api/chatbots/{chatbot_object['id']}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {"ok": True, "message": "Deleted chatbot test_chatbot2"}

    # Get all chatbots
    resp = test_app.get("/api/chatbots", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json == [chatbot_object3, chatbot_object2]


def test_chatbots_expired_file(
    test_app: TestClient,
    test_token: str,
    test_file_expired: FilePublic,
    test_chatbot_expired_file: ChatbotPublicWithFiles,
) -> None:
    # create a chatbot with expired file
    resp = test_app.post(
        "/api/chatbots",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "name": "test_chatbot",
            "description": "description",
            "system_prompt": "system_prompt",
            "citations_mode": False,
            "color": "green",
            "icon": "default",
            "files": [str(test_file_expired.id)],
        },
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    # get all chatbots
    resp = test_app.get(
        "/api/chatbots",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json()
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == str(test_chatbot_expired_file.id)
    assert resp.json()[0]["files"] == []
    chatbot_object = resp.json()[0]

    # get a chatbot
    resp = test_app.get(
        f"/api/chatbots/{chatbot_object['id']}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == chatbot_object
    assert resp.json()["files"] == []

    # add files to a chatbot (duplicate)
    resp = test_app.post(
        f"/api/chatbots/{chatbot_object['id']}",
        headers={"Authorization": f"Bearer {test_token}"},
        json=[str(test_file_expired.id)],
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.json()

    # change a chatbot
    resp = test_app.patch(
        f"/api/chatbots/{chatbot_object['id']}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "name": "test_chatbot2",
            "description": "description2",
            "color": "blue",
            "icon": "other",
            "system_prompt": "system_prompt2",
            "citations_mode": True,
            "files": [],
        },
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json
    assert json["name"] == "test_chatbot2"
    assert json["description"] == "description2"
    assert json["color"] == "blue"
    assert json["icon"] == "other"
    assert json["system_prompt"] == "system_prompt2"
    assert json["citations_mode"]
    assert json["files"] == []

    # add files to a chatbot
    resp = test_app.post(
        f"/api/chatbots/{chatbot_object['id']}",
        headers={"Authorization": f"Bearer {test_token}"},
        json=[str(test_file_expired.id)],
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    # delete a chatbot
    resp = test_app.delete(
        f"/api/chatbots/{chatbot_object['id']}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {"ok": True, "message": "Deleted chatbot test_chatbot2"}

    # Get all chatbots
    resp = test_app.get("/api/chatbots", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json == []


def test_create_chatbot_with_file_not_found(
    test_app: TestClient,
    test_token: str,
) -> None:
    # Attempt to create a chatbot with a non-existent file
    file_id = str(uuid7())
    resp = test_app.post(
        "/api/chatbots",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "name": "test_chatbot_with_nonexistent_file",
            "description": "description",
            "system_prompt": "system_prompt",
            "citations_mode": False,
            "color": "green",
            "icon": "default",
            "files": [file_id],  # Non-existent file ID
        },
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {
        "detail": {"error_code": "backend.error.file-s-not-found", "extra": {"file-ids-not-found": [file_id]}}
    }


def test_add_files_chatbot_not_found(
    test_app: TestClient,
    test_token: str,
    test_file: FilePublic,
) -> None:
    # Attempt to add files to a non-existent chatbot
    resp = test_app.post(
        f"/api/chatbots/{uuid7()}",
        headers={"Authorization": f"Bearer {test_token}"},
        json=[str(test_file.id)],
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.chatbot-not-found", "extra": {}}}


def test_add_files_files_not_found(
    test_app: TestClient,
    test_token: str,
    test_chatbot_admin: ChatbotPublicWithFiles,
) -> None:
    # Attempt to add files that do not exist to an existing chatbot
    file_id = str(uuid7())
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json=[file_id],
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {
        "detail": {"error_code": "backend.error.file-s-not-found", "extra": {"file-ids-not-found": [file_id]}}
    }


def test_add_files_duplicates(
    test_app: TestClient,
    test_token: str,
    test_chatbot_admin: ChatbotPublicWithFiles,
    test_file: FilePublic,
) -> None:
    # Attempt to add file that is already linked
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json=[str(test_file.id)],
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.json()
    assert resp.json() == {
        "detail": {
            "error_code": "backend.error.file-s_linked-to-chatbot",
            "extra": {"duplicate-file-ids": [str(test_file.id)]},
        }
    }


@pytest.mark.parametrize(
    ("file_fixture", "expected_error_code"),
    [
        ("test_file_status_pending", "backend.error.file-s-invalid-status"),
        ("test_file_status_failed", "backend.error.file-s-invalid-status"),
    ],
)
def test_add_files_invalid_status(
    test_app: TestClient,
    test_token: str,
    test_chatbot_admin: ChatbotPublicWithFiles,
    file_fixture: str,
    expected_error_code: str,
    request: pytest.FixtureRequest,
) -> None:
    test_file: FilePublic = request.getfixturevalue(file_fixture)

    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json=[str(test_file.id)],
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.json()
    assert resp.json() == {
        "detail": {
            "error_code": expected_error_code,
            "extra": {"file-s-invalid-status": [str(test_file.id)]},
        }
    }


def test_get_chatbot_not_found(
    test_app: TestClient,
    test_token: str,
) -> None:
    # Attempt to get a non-existent chatbot
    resp = test_app.get(
        f"/api/chatbots/{uuid7()}",  # Use an invalid ID
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.chatbot-not-found", "extra": {}}}


def test_patch_chatbot_not_found(
    test_app: TestClient,
    test_token: str,
) -> None:
    # Attempt to patch a non-existent chatbot
    resp = test_app.patch(
        f"/api/chatbots/{uuid7()}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "name": "new_name",
        },
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.chatbot-not-found", "extra": {}}}


def test_patch_chatbot_files_not_found(
    test_app: TestClient,
    test_token: str,
    test_chatbot_admin: ChatbotPublicWithFiles,
) -> None:
    # Attempt to patch a chatbot with files that do not exist
    file_id = str(uuid7())
    resp = test_app.patch(
        f"/api/chatbots/{test_chatbot_admin.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "files": [file_id],
        },
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {
        "detail": {"error_code": "backend.error.file-s-not-found", "extra": {"file-ids-not-found": [file_id]}}
    }


def test_delete_chatbot_not_found(
    test_app: TestClient,
    test_token: str,
) -> None:
    # Attempt to delete a non-existent chatbot
    resp = test_app.delete(
        f"/api/chatbots/{uuid7()}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.chatbot-not-found", "extra": {}}}


def test_add_group_to_chatbot(
    test_app: TestClient,
    test_token: str,
    test_fake_token: str,
    fake_user: UserPublic,
    test_group_factory: GroupFactory,
    test_chatbot_admin: ChatbotPublicWithFiles,
) -> None:
    group = test_group_factory()
    group_two = test_group_factory(owner=fake_user)

    # Add group to chatbot
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}/group/{group.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert len(resp.json()["groups"]) == 1
    assert resp.json()["groups"][0] == group.model_dump(mode="json", exclude={"chatbots"})

    # Chatbot not found
    resp = test_app.post(f"/api/chatbots/{uuid7()}/group/{group.id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.chatbot-not-found", "extra": {}}}

    # Group not found
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}/group/{uuid7()}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.group-not-found", "extra": {}}}

    # Not chatbot owner
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}/group/{group.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.not-authorized", "extra": {}}}

    # Not group member
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}/group/{group_two.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.not-authorized", "extra": {}}}


def test_remove_group_from_chatbot(
    test_app: TestClient,
    test_token: str,
    test_fake_token: str,
    fake_user: UserPublic,
    test_group_factory: GroupFactory,
    test_chatbot_admin: ChatbotPublicWithFiles,
) -> None:
    group = test_group_factory()

    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}/group/{group.id}", headers={"Authorization": f"Bearer {test_token}"}
    )

    # Delete group from chatbot
    resp = test_app.delete(
        f"/api/chatbots/{test_chatbot_admin.id}/group/{group.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert len(resp.json()["groups"]) == 0

    # Chatbot not found
    resp = test_app.delete(
        f"/api/chatbots/{uuid7()}/group/{group.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.chatbot-not-found", "extra": {}}}

    # Group not found
    resp = test_app.delete(
        f"/api/chatbots/{test_chatbot_admin.id}/group/{uuid7()}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.group-not-found", "extra": {}}}

    # Not chatbot owner
    resp = test_app.delete(
        f"/api/chatbots/{test_chatbot_admin.id}/group/{group.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.not-authorized", "extra": {}}}

    group_two = test_group_factory(owner=fake_user)
    # Not group member
    resp = test_app.delete(
        f"/api/chatbots/{test_chatbot_admin.id}/group/{group_two.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.not-authorized", "extra": {}}}


def test_add_user_to_chatbot(
    test_app: TestClient,
    test_token: str,
    test_fake_token: str,
    fake_user: UserPublic,
    test_chatbot_admin: ChatbotPublicWithFiles,
) -> None:
    # Add user to chatbot
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert len(resp.json()["individuals"]) == 1
    assert resp.json()["individuals"][0] == {
        "id": str(fake_user.id),
        "name": fake_user.name,
        "username": fake_user.username,
        "avatar": "https://www.example.com/favicon.png",
    }

    # Chatbot not found
    resp = test_app.post(
        f"/api/chatbots/{uuid7()}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.chatbot-not-found", "extra": {}}}

    # User not found
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}/user/{uuid7()}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.user-not-found", "extra": {}}}

    # Not chatbot owner
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}/user/{fake_user.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.not-authorized", "extra": {}}}


def test_remove_user_from_chatbot(
    test_app: TestClient,
    test_token: str,
    test_fake_token: str,
    fake_user: UserPublic,
    test_chatbot_admin: ChatbotPublicWithFiles,
) -> None:
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )

    # Remove user from chatbot
    resp = test_app.delete(
        f"/api/chatbots/{test_chatbot_admin.id}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert len(resp.json()["individuals"]) == 0

    # Chatbot not found
    resp = test_app.delete(
        f"/api/chatbots/{uuid7()}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.chatbot-not-found", "extra": {}}}

    # User not found
    resp = test_app.delete(
        f"/api/chatbots/{test_chatbot_admin.id}/user/{uuid7()}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.user-not-found", "extra": {}}}

    # Not chatbot owner
    resp = test_app.delete(
        f"/api/chatbots/{test_chatbot_admin.id}/user/{fake_user.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.not-authorized", "extra": {}}}


def test_chatbots_shared(
    test_app: TestClient,
    test_user: User,
    test_user_public: UserPublic,
    test_token: str,
    standard_user: UserPublic,
    test_user_token: str,
    test_chatbot: ChatbotPublic,
    test_group_factory: GroupFactory,
) -> None:
    def has_access(chatbot_id: ChatbotId, token: str, *, expected: bool) -> None:
        resp = test_app.post(
            "/api/conversations",
            json={"chatbot_id": str(chatbot_id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == status.HTTP_201_CREATED if expected else status.HTTP_403_FORBIDDEN, resp.json()

        resp = test_app.get(
            url="api/chatbots/shared",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == status.HTTP_200_OK, resp.json()
        if expected:
            assert str(chatbot_id) in [it["id"] for it in resp.json()]
        else:
            assert resp.json() == []

    # no access to other persons chatbot
    has_access(chatbot_id=test_chatbot.id, token=test_user_token, expected=False)

    # add user to a shared group and share the chatbot
    group = test_group_factory(member=[test_user, standard_user], owner=test_user)
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot.id}/group/{group.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # user should now have access
    has_access(chatbot_id=test_chatbot.id, token=test_user_token, expected=True)

    # try to share chatbot with the group again
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot.id}/group/{group.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.json()

    # remove group from chatbot
    resp = test_app.delete(
        f"/api/chatbots/{test_chatbot.id}/group/{group.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # user should no longer have access
    has_access(chatbot_id=test_chatbot.id, token=test_user_token, expected=False)

    # share chatbot with individual user
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot.id}/user/{standard_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # user should now have access again
    has_access(chatbot_id=test_chatbot.id, token=test_user_token, expected=True)

    # try to share chatbot again
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot.id}/user/{standard_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.json()

    # remove user from individuals
    resp = test_app.delete(
        f"/api/chatbots/{test_chatbot.id}/user/{standard_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # user should no longer have access
    has_access(chatbot_id=test_chatbot.id, token=test_user_token, expected=False)

    # try to share chatbot with yourself
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot.id}/user/{test_user_public.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.json()


def test_chatbots_share_normal_user(
    test_app: TestClient,
    standard_user: UserPublic,
    test_user_token: str,
    fake_user: UserPublic,
    test_group_factory: GroupFactory,
) -> None:
    # create a chatbot
    resp = test_app.post(
        "/api/chatbots",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={
            "name": "test_chatbot",
            "description": "description",
            "system_prompt": "system_prompt",
            "citations_mode": False,
            "color": "green",
            "icon": "default",
            "files": [],
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    chatbot_id = resp.json()["id"]

    # create group
    group = test_group_factory(owner=standard_user)

    # get all groups
    resp = test_app.get("/api/users/groups", headers={"Authorization": f"Bearer {test_user_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == [group.model_dump(mode="json", exclude={"created"})]

    # get all users
    resp = test_app.get("/api/users", headers={"Authorization": f"Bearer {test_user_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert len(resp.json()) > 1

    # share chatbot with group
    resp = test_app.post(
        f"/api/chatbots/{chatbot_id}/group/{group.id}", headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # share chatbot with individual
    resp = test_app.post(
        f"/api/chatbots/{chatbot_id}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()


def test_soft_deleted_chatbot_inaccessible(
    test_app: TestClient,
    test_token: str,
    test_chatbot_admin: ChatbotPublicWithFiles,
    test_file: FilePublic,
    test_group_factory: GroupFactory,
    fake_user: UserPublic,
    standard_user: UserPublic,
    test_user_token: str,
    test_llm: LLM,
) -> None:
    chatbot_id = test_chatbot_admin.id

    # create a conversation with that chatbot
    resp = test_app.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"chatbot_id": str(chatbot_id)},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    conversation_id = resp.json()["id"]

    # share chatbot with another user
    resp = test_app.post(
        f"/api/chatbots/{chatbot_id}/user/{standard_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # other user creates another conversation
    resp = test_app.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={"chatbot_id": str(chatbot_id)},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    other_conversation_id = resp.json()["id"]

    # Soft delete the chatbot
    resp = test_app.delete(
        f"/api/chatbots/{chatbot_id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {"ok": True, "message": f"Deleted chatbot {test_chatbot_admin.name}"}

    # Attempt to get the soft-deleted chatbot
    resp = test_app.get(
        f"/api/chatbots/{chatbot_id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.chatbot-not-found", "extra": {}}}

    # Ensure the soft-deleted chatbot doesn't appear in the chatbots list
    resp = test_app.get("/api/chatbots", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    chatbots = resp.json()
    assert not any(chatbot["id"] == str(chatbot_id) for chatbot in chatbots)

    # Ensure adding files to a soft-deleted chatbot fails
    resp = test_app.post(
        f"/api/chatbots/{chatbot_id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json=[str(test_file.id)],
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    # Ensure updating a soft-deleted chatbot fails
    resp = test_app.patch(
        f"/api/chatbots/{chatbot_id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "name": "updated_name",
            "description": "updated_description",
        },
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    # Ensure sharing a soft-deleted chatbot with a group fails
    group = test_group_factory()
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}/group/{group.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    # Ensure sharing a soft-deleted chatbot with an individual fails
    resp = test_app.post(
        f"/api/chatbots/{test_chatbot_admin.id}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    # Ensure creating new conversations with the chatbot fails
    resp = test_app.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"chatbot_id": str(chatbot_id)},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    # ensure creating a new message in an existing conversation with that chatbot fails
    resp = test_app.post(
        f"/api/chat/{conversation_id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"message": "A message", "llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text

    # also for other users
    resp = test_app.post(
        f"/api/chat/{other_conversation_id}",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={"message": "A message", "llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text
