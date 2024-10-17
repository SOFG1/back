from typing import Protocol, runtime_checkable

import pytest
from fastapi.datastructures import State
from pytest_mock import MockerFixture
from sqlmodel import Session, select
from starlette import status
from starlette.testclient import TestClient

from app.api.exceptions import IndexNotFoundError
from app.api.models import File, FilePublic, IndexingStatus
from app.api.routers.indexes import get_current_index_name
from tests.constants import (
    CURRENT_INDEX_EXPECTED_RESPONSE,
    CURRENT_INDEX_INVALID_STR_RESPONSE,
    CURRENTS_INDEX_VALID_STR_RESPONSE,
    LIST_OLD_COLLECTED_RESPONSE,
    MOCK_LIST_OLD_VALUES,
)


def test_endpoints_permissions(test_app: TestClient, test_user_token: str) -> None:
    resp = test_app.get("/api/indexes/old")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    resp = test_app.get("/api/indexes/old", headers={"Authorization": f"Bearer {test_user_token}"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    resp = test_app.get("/api/indexes/current")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    resp = test_app.get("/api/indexes/current", headers={"Authorization": f"Bearer {test_user_token}"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    resp = test_app.delete("/api/indexes/Tsai")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    resp = test_app.delete("/api/indexes/Tsai", headers={"Authorization": f"Bearer {test_user_token}"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    resp = test_app.get("/api/indexes/reindex/dry-run")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    resp = test_app.get("/api/indexes/reindex/dry-run", headers={"Authorization": f"Bearer {test_user_token}"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    resp = test_app.patch("/api/indexes/reindex")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    resp = test_app.patch("/api/indexes/reindex", headers={"Authorization": f"Bearer {test_user_token}"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()


def test_reindex_dry_run_endpoint(
    test_app: TestClient,
    test_token: str,
    test_file: FilePublic,  # noqa: ARG001
) -> None:
    response = test_app.get("/api/indexes/reindex/dry-run", headers={"Authorization": f"Bearer {test_token}"})
    assert response.status_code == status.HTTP_200_OK

    result = response.json()
    assert result == {"files_to_reindex": 1, "dry_run": True}


def test_reindex_endpoint(test_app: TestClient, test_token: str, test_file: FilePublic, db_session: Session) -> None:  # noqa: ARG001
    response = test_app.patch("/api/indexes/reindex", headers={"Authorization": f"Bearer {test_token}"})
    assert response.status_code == status.HTTP_200_OK
    file = db_session.execute(select(File)).scalar_one()
    assert file.indexing_status == IndexingStatus.PENDING
    result = response.json()
    assert result == {"files_to_reindex": 1, "dry_run": False}


@runtime_checkable
class AppWithState(Protocol):
    state: State


def test_list_old_indexes(
    test_app: TestClient,
    mocker: MockerFixture,
    test_token: str,
) -> None:
    assert isinstance(test_app.app, AppWithState)
    mocker.patch.object(test_app.app.state.weaviate_client.collections, "list_all", return_value=MOCK_LIST_OLD_VALUES)
    response = test_app.get("/api/indexes/old", headers={"Authorization": f"Bearer {test_token}"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == LIST_OLD_COLLECTED_RESPONSE


def test_delete_index_success(test_app: TestClient, mocker: MockerFixture, test_token: str) -> None:
    mocker.patch("app.api.routers.indexes.check_if_index_exists")
    index_name = "test_index"
    response = test_app.delete(f"/api/indexes/{index_name}", headers={"Authorization": f"Bearer {test_token}"})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"ok": True, "message": f"Index '{index_name}' successfully deleted."}


def test_delete_index_not_found(test_app: TestClient, mocker: MockerFixture, test_token: str) -> None:
    mocker.patch("app.api.routers.indexes.check_if_index_exists", side_effect=IndexNotFoundError())
    index_name = "non_existent_index"
    response = test_app.delete(f"/api/indexes/{index_name}", headers={"Authorization": f"Bearer {test_token}"})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": {"error_code": "backend.error.index-not-found", "extra": {}}}


def test_get_current_index_success(test_app: TestClient, mocker: MockerFixture, test_token: str) -> None:
    assert isinstance(test_app.app, AppWithState)
    mocker.patch.object(
        test_app.app.state.weaviate_client.collections, "get", return_value=CURRENTS_INDEX_VALID_STR_RESPONSE
    )
    response = test_app.get("/api/indexes/current", headers={"Authorization": f"Bearer {test_token}"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == CURRENT_INDEX_EXPECTED_RESPONSE


def test_convert_current_index_str_response_to_dict_no_json() -> None:
    with pytest.raises(ValueError, match="Could not find JSON structure in the string."):
        get_current_index_name(CURRENT_INDEX_INVALID_STR_RESPONSE)
