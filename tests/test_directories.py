from pathlib import Path

from fastapi import status
from fastapi.testclient import TestClient
from uuid6 import uuid7

from app.api.models import UserPublicDetailed
from tests.conftest import DirectoryFactory


def test_get_directory_not_authorized(
    test_app: TestClient, test_token: str, fake_user_detailed: UserPublicDetailed
) -> None:
    # attempt to get other users root directory - not authorized
    resp = test_app.get(
        f"/api/directories/{fake_user_detailed.root_directory.id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()


def test_get_directory(test_app: TestClient, test_fake_token: str, fake_user_detailed: UserPublicDetailed) -> None:
    # get root directory from profile
    resp = test_app.get(
        "/api/users/profile",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert "root_directory" in json
    assert "id" in json["root_directory"]
    assert json["root_directory"]["id"] == str(fake_user_detailed.root_directory.id)

    # get directory
    resp = test_app.get(
        f"/api/directories/{fake_user_detailed.root_directory.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    expected = fake_user_detailed.root_directory.model_dump(mode="json")
    expected.update({"children": [], "files": [], "parent": None})
    assert json == expected


def test_create_directory(test_app: TestClient, test_fake_token: str, fake_user_detailed: UserPublicDetailed) -> None:
    # create a new directory
    resp = test_app.post(
        "/api/directories",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={"name": "test_dir", "parent_id": str(fake_user_detailed.root_directory.id)},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = resp.json()
    assert json["name"] == "test_dir"
    assert json["parent_id"] == str(fake_user_detailed.root_directory.id)
    assert json["canonical"] == "/test_dir"

    # create a directory that already exists
    resp = test_app.post(
        "/api/directories",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={"name": "test_dir", "parent_id": str(fake_user_detailed.root_directory.id)},
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.json()
    assert resp.json()["detail"] == {"error_code": "backend.error.directory-exists", "extra": {}}


def test_move_directory(
    test_app: TestClient,
    test_fake_token: str,
    fake_user_detailed: UserPublicDetailed,
    test_directory_factory: DirectoryFactory,
) -> None:
    # create two new directories
    directory = test_directory_factory(name="test_dir")
    new_parent_directory = test_directory_factory(name="test_dir2")

    # move and rename a directory
    resp = test_app.patch(
        f"/api/directories/{directory.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={"name": "new_test_dir", "parent_id": str(new_parent_directory.id)},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json["name"] == "new_test_dir"
    assert json["parent_id"] == str(new_parent_directory.id)
    assert json["canonical"] == "/test_dir2/new_test_dir"

    # noop move
    resp = test_app.patch(
        f"/api/directories/{directory.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == json

    # try to move directory to existing name/place
    resp = test_app.patch(
        f"/api/directories/{directory.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={"name": "test_dir2", "parent_id": str(fake_user_detailed.root_directory.id)},
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.directory-exists", "extra": {}}}


def test_rename_root_directory_not_allowed(
    test_app: TestClient, test_fake_token: str, fake_user_detailed: UserPublicDetailed
) -> None:
    # Attempt to rename the root directory
    resp = test_app.patch(
        f"/api/directories/{fake_user_detailed.root_directory.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={"name": "new_root_name"},  # Root directory cannot be renamed
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.cant-move-root-directory", "extra": {}}}

    # Attempt to move the root directory
    resp = test_app.patch(
        f"/api/directories/{fake_user_detailed.root_directory.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={"parent_id": str(uuid7())},  # Root directory cannot be moved
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.cant-move-root-directory", "extra": {}}}


def test_delete_directory(test_app: TestClient, test_fake_token: str, test_directory_factory: DirectoryFactory) -> None:
    # create a directory
    directory = test_directory_factory()

    # delete a directory
    resp = test_app.delete(
        f"/api/directories/{directory.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {"ok": True, "message": None}


def test_delete_root_directory(
    test_app: TestClient, test_fake_token: str, fake_user_detailed: UserPublicDetailed
) -> None:
    # attempt to delete the root directory
    resp = test_app.delete(
        f"/api/directories/{fake_user_detailed.root_directory.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    assert resp.json()["detail"] == {"error_code": "backend.error.cant-delete-root-directory", "extra": {}}


def test_delete_directory_with_files_and_subdirectories(
    test_app: TestClient,
    test_fake_token: str,
    test_directory_factory: DirectoryFactory,
) -> None:
    # Create the parent directory
    parent_dir = test_directory_factory(name="parent_dir")
    # Create a subdirectory inside the parent directory
    sub_dir = test_directory_factory(name="sub_dir", parent_id=parent_dir.id)

    # Create a file inside the parent directory
    with Path("data/testdocs/test.pdf").open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
            data={"directory_id": str(parent_dir.id)},
        )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    file1_id = resp.json()["id"]

    # Create a file inside the subdirectory
    with Path("data/testdocs/test_copy.pdf").open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
            data={"directory_id": str(sub_dir.id)},
        )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    file2_id = resp.json()["id"]

    # Delete the parent directory
    resp = test_app.delete(
        f"/api/directories/{parent_dir.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {"ok": True, "message": None}

    # Check that the parent directory no longer exists
    resp = test_app.get(
        f"/api/directories/{parent_dir.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    # Check that the subdirectory no longer exists
    resp = test_app.get(
        f"/api/directories/{sub_dir.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    # Check that the files no longer exist
    resp = test_app.get(
        f"/api/files/{file1_id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()

    resp = test_app.get(
        f"/api/files/{file2_id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()


def test_directory_not_found(test_app: TestClient, test_token: str) -> None:
    # test getting a directory that doesn't exist
    directory_id = uuid7()
    resp = test_app.get(
        f"/api/directories/{directory_id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json()["detail"] == {
        "error_code": "backend.error.directory-not-found",
        "extra": {"id": str(directory_id)},
    }


def test_move_directory_creating_cycle_not_allowed(
    test_app: TestClient, test_fake_token: str, test_directory_factory: DirectoryFactory
) -> None:
    # Step 1: Create the parent directory under the root directory
    parent_directory = test_directory_factory(name="parent")

    # Step 2: Create the child directory under the parent directory
    child_directory = test_directory_factory(name="child", parent_id=parent_directory.id)

    # Step 3: Attempt to move the parent directory under its own child directory (which should create a cycle)
    resp = test_app.patch(
        f"/api/directories/{parent_directory.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={"name": "parent", "parent_id": str(child_directory.id)},
    )

    # Step 4: Assert that this operation is forbidden (cycle detection)
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.directory-cycle", "extra": {}}}
