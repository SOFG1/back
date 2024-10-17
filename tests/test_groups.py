from fastapi import status
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.api.models import ADMIN_ID, Group, User, UserPublic
from tests.conftest import GroupFactory


def test_create_group(test_app: TestClient, test_token: str, test_user_public: UserPublic) -> None:
    # Create group
    resp = test_app.post(
        "/api/groups",
        headers={"Authorization": f"Bearer {test_token}"},
        json={
            "name": "TestGroup",
            "description": "Test Group",
            "icon": "TestIcon",
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = resp.json()
    assert "id" in json
    id = json["id"]
    assert json == {
        "id": id,
        "chatbots": [],
        "name": "TestGroup",
        "description": "Test Group",
        "icon": "TestIcon",
        "member": [
            {
                "name": test_user_public.name,
                "username": test_user_public.username,
                "id": str(test_user_public.id),
                "avatar": "https://www.example.com/favicon.png",
            }
        ],
    }


def test_add_member_to_group(
    test_app: TestClient, test_token: str, fake_user: UserPublic, test_group_factory: GroupFactory, test_group: Group
) -> None:
    group = test_group_factory()

    # Add a member
    resp = test_app.post(
        f"/api/groups/{group.id}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {
        "id": str(group.id),
        "name": group.name,
        "description": group.description,
        "icon": group.icon,
        "member": [
            {"name": "Test", "username": "admin", "id": str(ADMIN_ID), "avatar": "https://www.example.com/favicon.png"},
            {
                "name": fake_user.name,
                "username": fake_user.username,
                "id": str(fake_user.id),
                "avatar": "https://www.example.com/favicon.png",
            },
        ],
    }

    # Try to add a second time
    resp = test_app.post(
        f"/api/groups/{group.id}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.user-in-group", "extra": {}}}
    # Group not found
    resp = test_app.post(
        f"/api/groups/{uuid7()}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.group-not-found", "extra": {}}}

    # user not found
    resp = test_app.post(f"/api/groups/{group.id}/user/{uuid7()}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.user-not-found", "extra": {}}}

    # try to add member to default group
    resp = test_app.post(
        f"/api/groups/{test_group.id}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.group-can-not-be-modified-manually", "extra": {}}}


def test_remove_member_from_group(
    test_app: TestClient, test_token: str, fake_user: UserPublic, test_group_factory: GroupFactory, test_group: Group
) -> None:
    group = test_group_factory(member=[fake_user])

    # Remove a member
    resp = test_app.delete(
        f"/api/groups/{group.id}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {
        "id": str(group.id),
        "name": group.name,
        "description": group.description,
        "icon": group.icon,
        "member": [],
    }
    # Modification error for default group
    resp = test_app.delete(
        f"/api/groups/{test_group.id}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.group-can-not-be-modified-manually", "extra": {}}}

    # Group not found
    resp = test_app.delete(
        f"/api/groups/{uuid7()}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.group-not-found", "extra": {}}}

    # user not found
    resp = test_app.delete(f"/api/groups/{group.id}/user/{uuid7()}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.user-not-found", "extra": {}}}


def test_update_group(
    test_app: TestClient, test_token: str, test_group_factory: GroupFactory, test_group: Group
) -> None:
    group = test_group_factory()

    # Update a group
    resp = test_app.patch(
        f"/api/groups/{group.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"name": "UpdateGroup", "description": "Update Group", "icon": "UpdateIcon"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {
        "id": str(group.id),
        "chatbots": [],
        "name": "UpdateGroup",
        "description": "Update Group",
        "icon": "UpdateIcon",
        "member": [
            {"name": "Test", "username": "admin", "id": str(ADMIN_ID), "avatar": "https://www.example.com/favicon.png"},
        ],
    }

    # Modification error for default group
    resp = test_app.patch(
        f"/api/groups/{test_group.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"name": "UpdateGroup", "description": "Update Group", "icon": "UpdateIcon"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.group-can-not-be-modified-manually", "extra": {}}}

    # Group not found
    resp = test_app.patch(
        f"/api/groups/{uuid7()}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"name": "BackUpdateGroup", "description": "BackUpdate Group", "icon": "BackUpdateIcon"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.group-not-found", "extra": {}}}


def test_delete_group(
    test_app: TestClient, test_token: str, test_group_factory: GroupFactory, test_group: Group
) -> None:
    group = test_group_factory()

    # Delete a group
    resp = test_app.delete(f"/api/groups/{group.id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {"ok": True, "message": f"Deleted group {group.name}"}
    # Modification error for default group
    resp = test_app.delete(f"/api/groups/{test_group.id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.group-can-not-be-deleted", "extra": {}}}

    # Group not found
    resp = test_app.delete(f"/api/groups/{group.id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.group-not-found", "extra": {}}}


def test_get_group(
    test_app: TestClient,
    test_token: str,
    test_group_factory: GroupFactory,
) -> None:
    group = test_group_factory()

    # Delete a group
    resp = test_app.get(f"/api/groups/{group.id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {
        "id": str(group.id),
        "chatbots": [],
        "name": "Finance",
        "description": "Just a finance group",
        "icon": "default",
        "member": [
            {"name": "Test", "username": "admin", "id": str(ADMIN_ID), "avatar": "https://www.example.com/favicon.png"}
        ],
    }

    # Group not found
    resp = test_app.get(f"/api/groups/{uuid7()}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.group-not-found", "extra": {}}}


def test_get_all_group(
    test_app: TestClient,
    test_token: str,
    test_group_factory: GroupFactory,
) -> None:
    finance, legal = (
        test_group_factory(name="Finance", description="the finance department"),
        test_group_factory(name="Legal", description="the legal department"),
    )

    # Get all groups for user
    resp = test_app.get("/api/groups", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == [
        {
            "id": str(legal.id),
            "chatbots": [],
            "name": legal.name,
            "description": legal.description,
            "icon": legal.icon,
            "member": [
                {
                    "name": "Test",
                    "username": "admin",
                    "id": str(ADMIN_ID),
                    "avatar": "https://www.example.com/favicon.png",
                }
            ],
        },
        {
            "id": str(finance.id),
            "chatbots": [],
            "name": finance.name,
            "description": finance.description,
            "icon": finance.icon,
            "member": [
                {
                    "name": "Test",
                    "username": "admin",
                    "id": str(ADMIN_ID),
                    "avatar": "https://www.example.com/favicon.png",
                }
            ],
        },
    ]


def test_group_not_authorized(
    test_app: TestClient,
    test_token: str,
    test_group_factory: GroupFactory,
    test_user: User,
    fake_user: UserPublic,
    standard_user: UserPublic,
) -> None:
    group = test_group_factory(owner=standard_user, member=[standard_user, test_user])

    resp = test_app.get("/api/groups", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert str(group.id) not in [g["id"] for g in resp.json()]

    resp = test_app.get("/api/users/groups", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert str(group.id) in [g["id"] for g in resp.json()]

    resp = test_app.post(
        f"/api/groups/{group.id}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    resp = test_app.patch(
        f"/api/groups/{group.id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"name": "BackUpdateGroup", "description": "BackUpdate Group", "icon": "BackUpdateIcon"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    resp = test_app.delete(
        f"/api/groups/{group.id}/user/{standard_user.id}", headers={"Authorization": f"Bearer {test_token}"}
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    resp = test_app.delete(f"/api/groups/{group.id}", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
