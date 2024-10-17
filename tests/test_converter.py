from pathlib import Path

from fastapi import status
from fastapi.testclient import TestClient

from app.engine.converter import Converter
from app.engine.indexer import Indexer
from tests.constants import NEW_INDEX_TEST_NAMESPACE


def test_converting_and_indexing_succeeds(test_app: TestClient, test_token: str) -> None:
    with Path("data/testdocs/docx/dienstreisen.md.docx").open("rb") as f:
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
    indexer = Indexer()
    indexer.initialize(NEW_INDEX_TEST_NAMESPACE)
    indexer.poll()
    resp = test_app.get(
        f"/api/files/{file_id}",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json()["file"]["indexing_status"] == "indexed", resp.json()
