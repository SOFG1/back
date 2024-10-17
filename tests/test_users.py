from collections.abc import Callable

import jwt
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, text
from uuid6 import uuid7

from app.api.models import ADMIN_ID, Group, LLMPublic, Scope, User, UserPublic
from app.settings import settings


def test_users(test_app: TestClient, test_token: str, test_group: Group, db_session: Session) -> None:
    # admin is already in a group by default
    assert len(test_group.member) == 1
    # register new user with default permissions
    username2 = "test2"
    resp = test_app.post(
        "/api/users/register",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"username": username2, "password": "test123", "name": "Test", "email": f"{username2}@skillbyte.de"},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = resp.json()
    assert json
    assert json["username"] == username2
    assert json["scopes"] == "chatbots,conversations,files,groups"
    test2_user_id = json["id"]
    # user was added to default group automatically
    db_session.refresh(test_group)
    assert len(test_group.member) == 2

    # create a new user with admin permissions
    username3 = "test3"
    resp = test_app.post(
        "/api/users",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "username": username3,
            "password": "test123",
            "name": "Test",
            "email": f"{username3}@skillbyte.de",
            "scopes": ["*"],
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = resp.json()
    assert json
    assert json["username"] == username3
    assert json["scopes"] == "*"
    db_session.refresh(test_group)
    # test_3 user was added to default group automatically
    assert len(test_group.member) == 3

    # get a token for a user
    token = get_token_for_user(test_app, username3, "test123")
    assert token
    decoded_token = jwt.decode(
        token, settings.oauth_secret_key.get_secret_value(), algorithms=[settings.oauth_algorithm]
    )
    assert decoded_token
    assert decoded_token["sub"] == username3

    # get a token for a user using email
    token = get_token_for_user(test_app, f"{username3}@skillbyte.de", "test123")
    assert token
    decoded_token = jwt.decode(
        token, settings.oauth_secret_key.get_secret_value(), algorithms=[settings.oauth_algorithm]
    )
    assert decoded_token
    assert decoded_token["sub"] == username3

    # list all users
    resp = test_app.get(
        "/api/users",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json
    assert len(json) == 3
    assert {user["username"] for user in json} == {"admin", "test2", "test3"}
    assert len(test_group.member) == 3
    # get the current user
    resp = test_app.get(
        "/api/users/profile",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json
    assert json["username"] == username3
    old_avatar = json["avatar"]

    # change password of current user
    resp = test_app.post(
        "/api/users/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": "test123", "new_password": "test1234"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json
    assert json["username"] == username3
    token = get_token_for_user(test_app, username3, "test1234")
    assert token

    # change avatar of current user
    resp = test_app.post(
        "/api/users/change-avatar",
        headers={"Authorization": f"Bearer {token}"},
        json={"avatar": "https://www.example.com/favicon2.png"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json
    assert json["username"] == username3
    avatar = json["avatar"]
    assert old_avatar != avatar
    assert avatar == "https://www.example.com/favicon2.png"

    # change name of current user
    resp = test_app.post(
        "/api/users/change-name",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "New Name"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    resp = test_app.get(
        "/api/users/profile",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json
    assert json["name"] == "New Name"

    # get another user
    resp = test_app.get(
        f"/api/users/{test2_user_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json
    assert json["username"] == "test2"

    # set another user's permissions
    resp = test_app.patch(
        f"/api/users/{test2_user_id}/scopes",
        headers={"Authorization": f"Bearer {token}"},
        json={"scopes": [Scope.FILES]},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json
    assert json["username"] == "test2"
    assert json["scopes"] == "files"

    # delete a user
    resp = test_app.delete(f"/api/users/{test2_user_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {
        "ok": True,
        "message": f"Deleted user {username2}, which had 0 file(s), 1 directory(s), 0 conversation(s), 0 message(s), 0 group(s) and 0 chatbot(s)",
    }


def test_register_user_exists(test_app: TestClient, test_token: str, test_group: Group) -> None:  # noqa: ARG001
    """Test that registering an existing user raises a conflict error."""
    resp = test_app.post(
        "/api/users/register",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"username": "admin1", "password": "test123", "name": "Admin User", "email": "admin1@skillbyte.de"},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    resp = test_app.post(
        "/api/users/register",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"username": "admin1", "password": "test123", "name": "Admin User", "email": "admin1@skillbyte.de"},
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.user-exists", "extra": {}}}


def test_create_user_exists(test_app: TestClient, test_token: str, test_group: Group) -> None:  # noqa: ARG001
    """Test that creating an existing user raises a conflict error."""
    resp = test_app.post(
        "/api/users",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"username": "admin1", "password": "test123", "name": "Admin User", "email": "admin1@skillbyte.de"},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    resp = test_app.post(
        "/api/users",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"username": "admin1", "password": "test123", "name": "Admin User", "email": "admin1@skillbyte.de"},
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.user-exists", "extra": {}}}


def test_login_incorrect_credentials(test_app: TestClient) -> None:
    """Test that logging in with incorrect credentials raises unauthorized error."""
    resp = test_app.post("/api/users/token", data={"username": "unknown", "password": "wrongpass"})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.invalid-user-provided-credentials", "extra": {}}}


def test_get_logged_in_user_unauthorized(test_app: TestClient) -> None:
    """Test getting the currently logged-in user without a token raises error."""
    resp = test_app.get("/api/users/profile")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    assert resp.json() == {"detail": "Not authenticated"}


def test_change_password_incorrect_old_password(test_app: TestClient, test_token: str) -> None:
    """Test changing password with incorrect old password raises unauthorized error."""
    resp = test_app.post(
        "/api/users/change-password",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"old_password": "wrong_old_pass", "new_password": "new_pass"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.incorrect-password", "extra": {}}}


def test_change_avatar_unauthorized(test_app: TestClient) -> None:
    """Test changing avatar without authorization raises error."""
    resp = test_app.post(
        "/api/users/change-avatar",
        json={"avatar": "https://www.example.com/avatar.png"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    assert resp.json() == {"detail": "Not authenticated"}


def test_get_user_profile_not_found(test_app: TestClient, test_token: str) -> None:
    """Test getting a non-existing user profile raises not found error."""
    resp = test_app.get(f"/api/users/{uuid7()}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.user-not-found", "extra": {}}}


def test_set_scopes_admin_permission(test_app: TestClient, test_token: str) -> None:
    """Test attempting to set scopes on the admin raises forbidden error."""
    resp = test_app.patch(
        f"/api/users/{ADMIN_ID}/scopes",  # Assuming admin has ID 1
        headers={"Authorization": f"Bearer {test_token}"},
        json={"scopes": ["users"]},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.cant-change-superadmin-permission", "extra": {}}}


def test_delete_admin_user(test_app: TestClient, test_token: str) -> None:
    """Test attempting to delete the admin user raises forbidden error."""
    resp = test_app.delete(f"/api/users/{ADMIN_ID}", headers={"Authorization": f"Bearer {test_token}"})  # ID 1 is admin
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.cant-delete-superadmin", "extra": {}}}


def get_token_for_user(test_app: TestClient, username: str, password: str) -> str:
    resp = test_app.post("/api/users/token", data={"username": username, "password": password})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json
    return json["access_token"]


def test_change_user_name_unauthorized(test_app: TestClient) -> None:
    """Test changing own user's name without authentication should return 401."""
    resp = test_app.post("/api/users/change-name", json={"name": "<NAME>"})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()


def test_groups_endpoint(test_app: TestClient, test_token: str, test_group_factory: Callable, test_user: User) -> None:
    resp = test_app.get(
        url="/api/users/groups",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == []

    group_1 = test_group_factory()
    group_2 = test_group_factory()

    resp = test_app.get(
        url="/api/users/groups",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert [it["id"] for it in resp.json()] == [str(group_2.id), str(group_1.id)]

    id_resp = test_app.get(
        url=f"/api/users/{test_user.id}/groups",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert id_resp.json() == resp.json()


def test_delete_user_with_objects(
    test_app: TestClient,
    test_user_public: UserPublic,
    test_token: str,
    test_group: Group,  # noqa: ARG001
    db_session: Session,
    test_llm: LLMPublic,
) -> None:
    # create a user
    username = "delete_test_user"
    resp = test_app.post(
        "/api/users/register",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "username": username,
            "password": "password123",
            "name": "Delete Test",
            "email": f"{username}@example.com",
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    user_id = resp.json()["id"]

    # Obtain a token for the new user
    user_token = get_token_for_user(test_app, username, "password123")

    # create a chatbot
    resp = test_app.post(
        "/api/chatbots",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "name": "Test Chatbot",
            "description": "A chatbot for testing deletion",
            "system_prompt": "You are a testbot",
            "color": "red",
            "icon": "default",
            "citations_mode": False,
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    chatbot1_id = resp.json()["id"]

    # create another chatbot
    resp = test_app.post(
        "/api/chatbots",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "name": "Test Chatbot",
            "description": "A chatbot for testing deletion",
            "system_prompt": "You are a testbot",
            "color": "red",
            "icon": "default",
            "citations_mode": False,
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    chatbot2_id = resp.json()["id"]

    # upload a file
    resp = test_app.post(
        "/api/files/upload",
        headers={"Authorization": f"Bearer {user_token}"},
        files={"file": ("test_file.pdf", b"Test file content", "application/pdf")},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = resp.json()
    file_user_id = json["id"]
    file_id = json["file"]["id"]

    # set the file to be indexed
    db_session.execute(
        text("""
        UPDATE file SET indexing_status = 'INDEXED'
        WHERE id = :file_id
        """),
        {"file_id": file_id},
    )
    db_session.commit()

    # link the chatbot to the file
    resp = test_app.post(
        f"/api/chatbots/{chatbot2_id}",
        headers={"Authorization": f"Bearer {user_token}"},
        json=[file_user_id],
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # create a conversation with the chatbot
    resp = test_app.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"chatbot_id": chatbot2_id},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    conversation_id = resp.json()["id"]

    # write a message
    resp = test_app.post(
        f"/api/chat/{conversation_id}",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"message": "Another message", "llm": str(test_llm.id)},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text

    # share the chatbot with another user
    resp = test_app.post(
        f"/api/chatbots/{chatbot2_id}/user/{test_user_public.id}", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # other user creates a conversation with the chatbot
    resp = test_app.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"chatbot_id": chatbot2_id},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    other_conversation_id = resp.json()["id"]

    # create a group
    resp = test_app.post(
        "/api/groups",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"name": "Test Group", "description": "A group for testing"},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    group_id = resp.json()["id"]

    # get user root directory
    resp = test_app.get("/api/users/profile", headers={"Authorization": f"Bearer {user_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    root_directory_id = resp.json()["root_directory"]["id"]

    # create a directory
    resp = test_app.post(
        "/api/directories",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"name": "Test Directory", "parent_id": root_directory_id},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    directory_id = resp.json()["id"]

    # delete the user
    resp = test_app.delete(
        f"/api/users/{user_id}",
        headers={"Authorization": f"Bearer {test_token}"},  # Use an admin token here
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {
        "ok": True,
        "message": f"Deleted user {username}, which had 1 file(s), 2 directory(s), 1 conversation(s), 2 message(s), 1 group(s) and 2 chatbot(s)",
    }

    # test that everything was removed
    resp = test_app.get(f"/api/chatbots/{chatbot1_id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    resp = test_app.get(f"/api/chatbots/{chatbot2_id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    resp = test_app.get(f"/api/files/{file_user_id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    resp = test_app.get(f"/api/conversations/{conversation_id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    resp = test_app.get(
        f"/api/conversations/{other_conversation_id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    resp = test_app.get(f"/api/groups/{group_id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    resp = test_app.get(f"/api/directories/{directory_id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    resp = test_app.get(f"/api/users/{user_id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
