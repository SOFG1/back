import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture
from sqlmodel import Session
from uuid6 import uuid7
from weaviate.exceptions import WeaviateConnectionError

from app.api import exceptions
from app.api.models import FilePublic, UserPublic, UserPublicDetailed
from app.api.routers.files import MAX_FILE_SIZE_MB, get_user_files_by_file_ids, object_store
from app.engine.converter import Converter
from tests.conftest import AddFile, DirectoryFactory, GroupFactory


def test_files_not_authorized(test_app: TestClient, test_fake_token: str, test_file: FilePublic) -> None:
    # download the file - not authorized
    resp = test_app.get(
        f"/api/files/download/{test_file.id}/test.pdf",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    # get a file - not authorized
    resp = test_app.get(
        f"/api/files/{test_file.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    # patch the file - not authorized
    resp = test_app.patch(
        f"/api/files/{test_file.id}",
        json={},
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    # reupload the file - not authorized
    with Path("data/testdocs/test_copy.pdf").open("rb") as f:
        resp = test_app.patch(
            f"/api/files/reupload/{test_file.id}",
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # reindex the file - not authorized
    resp = test_app.patch(
        f"/api/files/{test_file.id}/reindex",
        json=None,
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    # delete the file - not authorized
    resp = test_app.delete(
        f"/api/files/{test_file.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    # get all files again to see our ownerships
    resp = test_app.get(
        "/api/files",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json == []


def test_files(test_app: TestClient, test_fake_token: str, test_file: FilePublic) -> None:
    # upload a file
    with Path("data/testdocs/test_copy.pdf").open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = file_object = resp.json()
    assert json
    assert json["file_name"] == "test_copy.pdf"
    assert json["file"]["mime_type"] == "application/pdf"
    assert json["file"]["indexing_status"] == "pending"
    file_object["file"]["indexing_status"] = "indexed"

    # download the file
    resp = test_app.get(
        f"/api/files/download/{file_object['id']}/test_copy.pdf",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.read()

    # get all files (test_file is not included, because of another owner)
    resp = test_app.get(
        "/api/files",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    json[0]["file"]["indexing_status"] = "indexed"
    assert json == [file_object]

    # get a file
    resp = test_app.get(
        f"/api/files/{file_object['id']}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    json["file"]["indexing_status"] = "indexed"
    assert json == file_object

    # reindex the file
    resp = test_app.patch(
        f"/api/files/{file_object['id']}/reindex",
        json=None,
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    json = resp.json()
    assert json["file"]["indexing_status"] == "pending"
    json["file"]["indexing_status"] = "indexed"
    assert json == file_object

    # delete the file
    resp = test_app.delete(
        f"/api/files/{file_object['id']}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == {
        "ok": True,
        "message": "File test_copy.pdf deleted successfully.",
    }

    # upload test.pdf as current user to get ownership
    with Path("data/testdocs/test.pdf").open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = resp.json()
    assert json
    assert json["file_name"] == "test.pdf"
    assert json["file"]["mime_type"] == "application/pdf"
    assert json["file"]["indexing_status"] == "indexed"  # is already indexed, because of already uploaded

    # get all files again (this time we got ownership of test.pdf)
    resp = test_app.get(
        "/api/files",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    # can only check length and file, because both have different FileUser because uploaded after each other
    assert len(json) == 1
    assert json[0]["file"] == test_file.model_dump(mode="json")["file"]


def test_files_expired(test_app: TestClient, test_token: str, test_file_expired: FilePublic) -> None:
    # upload a file
    with Path("data/testdocs/test_copy.pdf").open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {test_token}"},
            files={"file": f},
            data={"expires": test_file_expired.expires.isoformat()} if test_file_expired.expires else None,
        )
    assert resp.status_code == status.HTTP_410_GONE, resp.json()

    # download the file
    resp = test_app.get(
        f"/api/files/download/{test_file_expired.id}/test_copy.pdf",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_410_GONE, resp.json()

    # get all files, test_file_expired is not included
    resp = test_app.get(
        "/api/files",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert test_file_expired.model_dump(mode="json") not in resp.json()

    # get a file
    resp = test_app.get(
        f"/api/files/{test_file_expired.id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_410_GONE, resp.json()

    # reindex the file
    resp = test_app.patch(
        f"/api/files/{test_file_expired.id}/reindex",
        json=None,
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_410_GONE, resp.json()

    # reupload an expired file
    with Path("data/testdocs/test_copy_copy.pdf").open("rb") as f:
        resp = test_app.patch(
            f"/api/files/reupload/{test_file_expired.id}",
            headers={"Authorization": f"Bearer {test_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_410_GONE

    # delete the file
    resp = test_app.delete(
        f"/api/files/{test_file_expired.id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_410_GONE, resp.json()

    # upload a file that will expire in the future
    expires = datetime.now(UTC) + timedelta(days=1)
    with Path("data/testdocs/test_copy.pdf").open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {test_token}"},
            files={"file": f},
            data={"expires": expires.isoformat()},
        )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = resp.json()
    assert json["expires"] == expires.isoformat().replace("+00:00", "Z")
    file_id = json["id"]

    # change the file to expire later
    expires += timedelta(days=1)
    resp = test_app.patch(
        f"/api/files/{file_id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"expires": expires.isoformat()},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    test_file_not_yet_expired = resp.json()
    assert test_file_not_yet_expired["expires"] == expires.isoformat().replace("+00:00", "Z")

    # the not-expired file is included in the list of files
    resp = test_app.get(
        "/api/files",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert test_file_not_yet_expired in resp.json()

    # change the file to no longer expire
    resp = test_app.patch(
        f"/api/files/{file_id}",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"expires": None},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json()["expires"] is None


def test_reupload(test_app: TestClient, test_fake_token: str, test_file: FilePublic) -> None:  # noqa: ARG001
    # upload a file
    with Path("data/testdocs/test_copy.pdf").open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_201_CREATED
    json = file_object = resp.json()
    assert json
    assert json["file_name"] == "test_copy.pdf"
    assert json["file"]["mime_type"] == "application/pdf"
    assert json["file"]["indexing_status"] == "pending"
    file_object["file"]["indexing_status"] = "indexed"

    # get all files (test_file is not included, because of another owner)
    resp = test_app.get(
        "/api/files",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    json = resp.json()
    json[0]["file"]["indexing_status"] = "indexed"
    assert json == [file_object]

    # reupload file with content of another file - file was never uploaded
    with Path("data/testdocs/3-kurzes-update.md.pdf").open("rb") as f:
        resp = test_app.patch(
            f"/api/files/reupload/{file_object.get('id')}",
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_201_CREATED
    json = file_object1 = resp.json()
    assert json
    assert json["file_name"] == "test_copy.pdf"  # because of reupload, the file name stays the same as before
    assert json["file"]["file_size"] != file_object["file"]["file_size"]  # file size has to be changed
    assert json["file"]["mime_type"] == "application/pdf"
    assert json["file"]["indexing_status"] == "pending"  # is already indexed, because of already uploaded

    # reupload file with content of another file - file was already uploaded by someone else
    with Path("data/testdocs/test.pdf").open("rb") as f:
        resp = test_app.patch(
            f"/api/files/reupload/{file_object.get('id')}",
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_201_CREATED
    json = file_object2 = resp.json()
    assert json
    assert json["file_name"] == "test_copy.pdf"  # because of reupload, the file name stays the same as before
    assert json["file"]["file_size"] != file_object1["file"]["file_size"]  # file size has to be changed
    assert json["file"]["mime_type"] == "application/pdf"
    assert json["file"]["indexing_status"] == "indexed"  # is already indexed, because of already uploaded

    # get all files (test_file is not included, because of another owner)
    resp = test_app.get(
        "/api/files",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    json = resp.json()
    json[0]["file"]["indexing_status"] = "indexed"
    assert json == [file_object2]

    # reupload file with no changes
    with Path("data/testdocs/test.pdf").open("rb") as f:
        resp = test_app.patch(
            f"/api/files/reupload/{file_object.get('id')}",
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.json() == {"detail": {"error_code": "backend.error.file-exists-for-user", "extra": {}}}


def test_reupload_delete_fails(
    test_app: TestClient, test_token: str, test_file: FilePublic, mocker: MockerFixture
) -> None:
    mocker.patch(
        "app.api.routers.files.delete_file_with_cleanup",
        return_value=WeaviateConnectionError(message="Failed to delete."),
    )
    with Path("data/testdocs/3-kurzes-update.md.pdf").open("rb") as f:
        resp = test_app.patch(
            f"/api/files/reupload/{test_file.id}",
            headers={"Authorization": f"Bearer {test_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.json() == {"detail": {"error_code": "backend.error.unable-to-delete-file", "extra": {}}}


def test_upload_file_too_large(test_app: TestClient, test_token: str, test_file: FilePublic) -> None:
    # Create a temporary file larger than the limit (50 MB)
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"x" * ((MAX_FILE_SIZE_MB + 1) * 1024**2))  # Create a 51 MB file
        temp_file_path = Path(temp_file.name)
    try:
        with temp_file_path.open("rb") as f:
            resp = test_app.post(
                "/api/files/upload",
                headers={"Authorization": f"Bearer {test_token}"},
                files={"file": f},
            )

        assert resp.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, resp.json()
        assert resp.json() == {
            "detail": {
                "error_code": "backend.error.file-too-large",
                "extra": {"actual-file-size-mb": 51.0, "max-file-size-mb": 50},
            }
        }

        with temp_file_path.open("rb") as f:
            resp = test_app.patch(
                f"/api/files/reupload/{test_file.id}",
                headers={"Authorization": f"Bearer {test_token}"},
                files={"file": f},
            )

        assert resp.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        assert resp.json() == {
            "detail": {
                "error_code": "backend.error.file-too-large",
                "extra": {"actual-file-size-mb": 51.0, "max-file-size-mb": 50},
            }
        }
    finally:
        temp_file_path.unlink()


def test_upload_file_unsupported_media_type(test_app: TestClient, test_token: str, test_file: FilePublic) -> None:
    # Create a temporary file with unsupported media type
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Hello, World!")  # Creating a simple text file
        temp_file_path = Path(temp_file.name)

    try:
        with temp_file_path.open("rb") as f:
            resp = test_app.post(
                "/api/files/upload",
                headers={"Authorization": f"Bearer {test_token}"},
                files={"file": f},
            )

        assert resp.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, resp.json()
        assert resp.json() == {
            "detail": {
                "error_code": "backend.error.unsupported-media-type",
                "extra": {"detected-media-type": "application/octet-stream"},
            }
        }

        with temp_file_path.open("rb") as f:
            resp = test_app.patch(
                f"/api/files/reupload/{test_file.id}",
                headers={"Authorization": f"Bearer {test_token}"},
                files={"file": f},
            )

        assert resp.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        assert resp.json() == {
            "detail": {
                "error_code": "backend.error.unsupported-media-type",
                "extra": {"detected-media-type": "application/octet-stream"},
            }
        }
    finally:
        temp_file_path.unlink()  # Clean up the temporary file


def test_upload_existing_file_already_ownership(test_app: TestClient, test_token: str, test_file: FilePublic) -> None:
    # Attempt to upload the same file again
    with Path("data/testdocs/test.pdf").open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {test_token}"},
            files={"file": f},
        )

    # Check that it responds with a conflict due to the existing file
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.file-exists-for-user", "extra": {}}}

    # get all files (just to remove ruff error)
    resp = test_app.get(
        "/api/files",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert test_file.model_dump(mode="json") in json


def test_download_file_not_found(test_app: TestClient, test_token: str) -> None:
    resp = test_app.get(
        f"/api/files/download/{uuid7()}/test.pdf",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.file-not-found", "extra": {}}}


def test_get_file_not_found(test_app: TestClient, test_token: str) -> None:
    resp = test_app.get(
        f"/api/files/{uuid7()}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.file-not-found", "extra": {}}}


def test_patch_file_not_found(test_app: TestClient, test_token: str) -> None:
    resp = test_app.patch(
        f"/api/files/{uuid7()}",
        json={},
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.file-not-found", "extra": {}}}


def test_reupload_file_not_found(test_app: TestClient, test_token: str) -> None:
    with Path("data/testdocs/test.pdf").open("rb") as f:
        resp = test_app.patch(
            f"/api/files/reupload/{uuid7()}",
            headers={"Authorization": f"Bearer {test_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json() == {"detail": {"error_code": "backend.error.file-not-found", "extra": {}}}


def test_reindex_file_not_found(test_app: TestClient, test_token: str) -> None:
    resp = test_app.patch(
        f"/api/files/{uuid7()}/reindex",
        json={},
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.file-not-found", "extra": {}}}


def test_delete_file_not_found(test_app: TestClient, test_token: str) -> None:
    resp = test_app.delete(
        f"/api/files/{uuid7()}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.file-not-found", "extra": {}}}


def test_directory_support(test_app: TestClient, fake_user_detailed: UserPublicDetailed, test_fake_token: str) -> None:
    # create a directory for the file
    resp = test_app.post(
        "/api/directories",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={"name": "foo", "parent_id": str(fake_user_detailed.root_directory.id)},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    directory_id = resp.json()["id"]

    # upload a file
    with Path("data/testdocs/test_copy.pdf").open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
            data={"directory_id": directory_id},
        )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = resp.json()
    assert json["file_name"] == "test_copy.pdf"
    assert json["directory"]["id"] == directory_id
    assert json["directory"]["canonical"] == "/foo"

    # upload a file to a non-existing directory
    with Path("data/testdocs/test_copy.pdf").open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
            data={"directory_id": str(uuid7())},
        )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()


def test_move_file(test_app: TestClient, test_fake_token: str, test_directory_factory: DirectoryFactory) -> None:
    # upload a file
    with Path("data/testdocs/test_copy.pdf").open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            params={"directory": "foo/bar"},
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    json = resp.json()
    file_id = json["id"]
    directory_id = json["directory"]["id"]

    # create a directory to move the file to
    directory = test_directory_factory(name="foo", parent_id=UUID(directory_id))

    # move and rename file
    resp = test_app.patch(
        f"/api/files/{file_id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={"file_name": "test.pdf", "directory_id": str(directory.id)},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert json["file_name"] == "test.pdf"
    assert json["directory"]["canonical"] == "/foo"
    assert json["modified"] > json["created"]

    # move file to non-existing directory
    resp = test_app.patch(
        f"/api/files/{file_id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={"file_name": "test.pdf", "directory_id": str(uuid7())},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()


def test_move_file_already_exists(test_app: TestClient, test_fake_token: str) -> None:
    # upload a file
    with Path("data/testdocs/test.pdf").open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            params={"directory": "foo/bar"},
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()

    # upload another file
    with Path("data/testdocs/test_copy.pdf").open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            params={"directory": "foo/bar"},
            headers={"Authorization": f"Bearer {test_fake_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    file_id = resp.json()["id"]

    # move file to existing file name
    resp = test_app.patch(
        f"/api/files/{file_id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
        json={"file_name": "test.pdf"},
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.json()


def test_get_user_files_by_file_ids(fake_user: UserPublic, db_session: Session, add_file: AddFile) -> None:
    with pytest.raises(exceptions.TsaiFileNotFoundError):
        get_user_files_by_file_ids(
            file_ids=[uuid7()],
            file_owner_id=fake_user.id,
            session=db_session,
        )

    public_file_1 = add_file(
        path=Path("data/testdocs/1-die-ersten-news.md.pdf"), user=fake_user, file_name="first-news.pdf"
    )
    public_file_2 = add_file(
        path=Path("data/testdocs/2-newsletter-nr-2.md.pdf"), user=fake_user, file_name="seconds-news.pdf"
    )

    assert public_file_1.file.id
    user_files = get_user_files_by_file_ids(
        file_ids=[public_file_1.file.id],
        session=db_session,
        file_owner_id=fake_user.id,
    )
    assert len(user_files) == 1
    assert user_files[0].id == public_file_1.id

    assert public_file_2.file.id
    user_files = get_user_files_by_file_ids(
        file_ids=[public_file_1.file.id, public_file_2.file.id],
        session=db_session,
        file_owner_id=fake_user.id,
    )
    assert len(user_files) == 2
    assert {it.id for it in user_files} == {public_file_1.id, public_file_2.id}

    # wrong user
    with pytest.raises(exceptions.TsaiFileNotFoundError):
        get_user_files_by_file_ids(
            file_ids=[public_file_1.id],
            file_owner_id=uuid7(),
            session=db_session,
        )

    # empty file list
    assert (
        get_user_files_by_file_ids(
            file_ids=[],
            session=db_session,
            file_owner_id=fake_user.id,
        )
        == []
    )


def test_deleting_pdf_file_succeeds(test_app: TestClient, test_token: str, mocker: MockerFixture) -> None:
    test_file = "data/testdocs/1-die-ersten-news.md.pdf"

    delete_spy = mocker.spy(object_store, "delete_object")

    with Path(test_file).open("rb") as f:
        resp = test_app.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {test_token}"},
            files={"file": f},
        )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    file_id = resp.json()["id"]
    assert file_id is not None

    converter = Converter()
    converter.poll()

    delete_spy.assert_not_called()

    resp = test_app.delete(
        f"/api/files/{file_id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )

    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert delete_spy.call_count == 1

    resp = test_app.get(
        f"/api/files/{file_id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.file-not-found", "extra": {}}}


def test_deleting_docx_file_succeeds(test_app: TestClient, test_token: str, mocker: MockerFixture) -> None:
    test_file = "data/testdocs/docx/dienstreisen.md.docx"

    delete_spy = mocker.spy(object_store, "delete_object")

    with (
        Path(test_file).open("rb") as f,
        patch("app.engine.converter.GotenbergClient", MagicMock()) as mock_gotenberg_client,
    ):
        mock_gotenberg_client.return_value.__enter__.return_value.libre_office.to_pdf.return_value.__enter__.return_value.pdf_format.return_value.convert.return_value.run.return_value.content = b"PDF"
        resp_created = test_app.post(
            "/api/files/upload",
            headers={"Authorization": f"Bearer {test_token}"},
            files={"file": f},
        )
        assert resp_created.status_code == status.HTTP_201_CREATED
        file_id = resp_created.json()["id"]
        assert file_id is not None

        converter = Converter()
        converter.poll()

        delete_spy.assert_not_called()

    resp = test_app.delete(
        f"/api/files/{file_id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )

    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert delete_spy.call_count == 2

    resp = test_app.get(
        f"/api/files/{file_id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.json()
    assert resp.json() == {"detail": {"error_code": "backend.error.file-not-found", "extra": {}}}


def test_file_shared_via_chatbot_and_no_patch_delete_rights(
    test_app: TestClient,
    test_file: FilePublic,
    test_user_token: str,
    fake_user: UserPublic,
    test_fake_token: str,
    test_group_factory: GroupFactory,
    standard_user: UserPublic,
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
            "files": [str(test_file.id)],
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.json()
    chatbot_id = resp.json()["id"]

    # Share this bot with fake_user
    resp = test_app.post(
        f"/api/chatbots/{chatbot_id}/user/{fake_user.id}", headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # Get shared file from fake_user
    resp = test_app.get(
        f"/api/files/{test_file.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    # Download shared file from fake_user
    resp = test_app.get(
        f"/api/files/download/{test_file.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.content

    # Download shared file from fake_user by id and name
    resp = test_app.get(
        f"/api/files/download/{test_file.id}/{test_file.file_name}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.content
    # Update shared file failed.  Permissions denied
    resp = test_app.patch(
        f"/api/files/{test_file.id}",
        json={},
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    # Delete shared file failed. Permissions denied
    resp = test_app.delete(
        f"/api/files/{test_file.id}",
        headers={"Authorization": f"Bearer {test_fake_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    # create group
    group = test_group_factory(owner=standard_user)
    # share chatbot with group
    resp = test_app.post(
        f"/api/chatbots/{chatbot_id}/group/{group.id}", headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()

    # Get shared file from  group member
    resp = test_app.get(
        f"/api/files/{test_file.id}",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    # Download shared file from  group member
    resp = test_app.get(
        f"/api/files/download/{test_file.id}",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.content

    # Download shared file from  group member by id and name
    resp = test_app.get(
        f"/api/files/download/{test_file.id}/{test_file.file_name}",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.content
    # Update shared file from group member failed.  Permissions denied
    resp = test_app.patch(
        f"/api/files/{test_file.id}",
        json={},
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
    # Delete shared file from group member failed. Permissions denied
    resp = test_app.delete(
        f"/api/files/{test_file.id}",
        headers={"Authorization": f"Bearer {test_user_token}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()
