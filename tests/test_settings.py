from datetime import UTC, datetime

from fastapi import status
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture
from sqlmodel import Session, select

from app.api.models import LLM, AdminSetting, LLMProvider
from app.settings import AdminSettings, _llm_cache, settings


def test_admin_settings_init(monkeypatch) -> None:  # noqa:ANN001
    monkeypatch.setenv("default_llm_display_name", "defaultllm")
    admin_settings = AdminSettings()  # type: ignore[reportCallIssue]
    assert admin_settings.default_llm_display_name == "defaultllm"

    admin_settings = AdminSettings(default_llm_display_name="myllm")  # type: ignore[reportCallIssue]
    assert admin_settings.default_llm_display_name == "myllm"


def test_admin_settings_to_list_conversions() -> None:
    admin_settings = AdminSettings(default_llm_display_name="myllm", default_llm_temperature=0.8)  # type: ignore[reportCallIssue]
    admin_setting_list = [
        AdminSetting(key="default_llm_display_name", value="myllm"),
        AdminSetting(key="default_llm_provider", value="openai", created=None, modified=None),
        AdminSetting(key="default_llm_model_name", value="gpt-4o", created=None, modified=None),
        AdminSetting(key="default_llm_title_model_name", value="gpt-4o-mini", created=None, modified=None),
        AdminSetting(key="default_llm_temperature", value="0.8"),
        AdminSetting(key="default_llm_title_temperature", value="0.01", created=None, modified=None),
        AdminSetting(key="default_llm_max_tokens", value="800", created=None, modified=None),
        AdminSetting(key="default_llm_top_p", value="0.95", created=None, modified=None),
        AdminSetting(key="default_llm_context_length", value="0", created=None, modified=None),
        AdminSetting(key="embedding_provider", value="openai", created=None, modified=None),
        AdminSetting(key="embedding_model", value="text-embedding-3-small", created=None, modified=None),
        AdminSetting(key="weaviate_index_prefix", value="default_index", created=None, modified=None),
    ]

    assert admin_settings.to_admin_setting_list() == admin_setting_list
    assert AdminSettings.from_admin_setting_list(admin_setting_list) == admin_settings


def test_to_and_from_db(db_session: Session) -> None:
    start = datetime.now(tz=UTC)
    admin_settings = AdminSettings(default_llm_display_name="myllm")  # type: ignore[reportCallIssue]
    admin_settings.to_db(session=db_session)

    db_out = db_session.exec(select(AdminSetting)).all()
    assert len(db_out) == 12
    example_row = [it for it in db_out if it.key == "default_llm_display_name"][0]  # noqa: RUF015
    assert example_row.value == "myllm"
    assert example_row.modified
    assert datetime.now(tz=UTC) > example_row.modified > start

    assert AdminSettings.from_db(session=db_session) == admin_settings


def test_endpoints_permissions(test_app: TestClient, test_user_token: str) -> None:
    resp = test_app.get("/api/settings")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    resp = test_app.get("/api/settings", headers={"Authorization": f"Bearer {test_user_token}"})
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()

    resp = test_app.post("/api/settings", json={})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.json()
    resp = test_app.post("/api/settings", headers={"Authorization": f"Bearer {test_user_token}"}, json={})
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.json()


def test_endpoints(test_app: TestClient, test_token: str, db_session: Session) -> None:
    # check if env-variables work as fallback if not present in DB
    resp = test_app.get("/api/settings", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    original_settings = {
        "default_llm_context_length": 0,
        "default_llm_display_name": "OpenAI GPT-4o",
        "default_llm_max_tokens": 800,
        "default_llm_model_name": "gpt-4o",
        "default_llm_provider": "openai",
        "default_llm_temperature": 0.01,
        "default_llm_title_model_name": "gpt-4o-mini",
        "default_llm_title_temperature": 0.01,
        "default_llm_top_p": 0.95,
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "weaviate_index_prefix": "default_index",
    }
    assert resp.json() == original_settings
    db_content = db_session.exec(select(AdminSetting)).all()
    assert len(db_content) == 0

    new_settings = {
        "default_llm_context_length": 14,
        "default_llm_display_name": "OpenAI GPT-4o mini",
        "default_llm_max_tokens": 800,
        "default_llm_model_name": "gpt-4o-mini",
        "default_llm_provider": "openai",
        "default_llm_temperature": 0.01,
        "default_llm_title_model_name": "gpt-4o-mini",
        "default_llm_title_temperature": 0.01,
        "default_llm_top_p": 0.95,
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "weaviate_index_prefix": "new_index",
    }
    # invalid model/provider was chosen
    new_settings["embedding_provider"] = "local"
    resp = test_app.post("/api/settings", headers={"Authorization": f"Bearer {test_token}"}, json=new_settings)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.json() == {"detail": {"error_code": "backend.error.not-valid-provider-model", "extra": {}}}

    # change settings
    new_settings["embedding_provider"] = "openai"
    resp = test_app.post("/api/settings", headers={"Authorization": f"Bearer {test_token}"}, json=new_settings)
    assert resp.status_code == status.HTTP_202_ACCEPTED, resp.json()
    db_content = db_session.exec(select(AdminSetting)).all()
    assert len(db_content) == 12

    # check if update worked
    resp = test_app.get("/api/settings", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == new_settings

    # change settings back
    resp = test_app.post("/api/settings", headers={"Authorization": f"Bearer {test_token}"}, json=original_settings)
    assert resp.status_code == status.HTTP_202_ACCEPTED, resp.json()

    # check if update worked
    resp = test_app.get("/api/settings", headers={"Authorization": f"Bearer {test_token}"})
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    assert resp.json() == original_settings


def test_llm(mocker: MockerFixture) -> None:
    _llm_cache.clear()
    assert len(_llm_cache) == 0
    spy = mocker.spy(settings, "_llm")

    llm_db = LLM(
        display_name="Test",
        provider=LLMProvider.BEDROCK,
        llm_model_name="TestModel",
        title_model_name="TestTitleModel",
        temperature=0.12,
        title_temperature=0.14,
        max_tokens=4000,
        top_p=0.2,
        context_length=42,
    )

    llm = settings.llm(llm_db)
    assert _llm_cache["chat"][llm_db.id] == llm
    spy.assert_called_once()

    # check cache usage
    _ = settings.llm(llm_db)
    spy.assert_called_once()


def test_title_llm(mocker: MockerFixture) -> None:
    _llm_cache.clear()
    assert len(_llm_cache) == 0
    spy = mocker.spy(settings, "_title_llm")

    llm_db = LLM(
        display_name="Test",
        provider=LLMProvider.BEDROCK,
        llm_model_name="TestModel",
        title_model_name="TestTitleModel",
        temperature=0.12,
        title_temperature=0.14,
        max_tokens=4000,
        top_p=0.2,
        context_length=42,
    )

    llm = settings.title_llm(llm_db)
    assert _llm_cache["title"][llm_db.id] == llm
    spy.assert_called_once()

    # check cache usage
    _ = settings.title_llm(llm_db)
    spy.assert_called_once()
