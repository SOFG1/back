from unittest.mock import AsyncMock, Mock

import httpx
from pytest_mock import MockFixture

# Mock settings.langfuse_host, settings.langfuse_public_key, and settings.langfuse_secret_key
from app.langfuse_bedrock import USER_MODELS, add_model, get_models, setup_langfuse_prices  # Adjust as per module
from app.settings import settings


async def test_get_models_success(mocker: MockFixture) -> None:
    # Mock the HTTP response
    mock_response_data = {
        "data": [{"modelName": "meta.llama3-1-8b-instruct-v1:0", "isLangfuseManaged": False}],
        "meta": {"totalPages": 1},
    }

    mock_get = mocker.patch(
        "httpx.AsyncClient.get",
        return_value=AsyncMock(json=Mock(return_value=mock_response_data), raise_for_status=Mock(return_value=None)),
    )
    client = httpx.AsyncClient()

    user_model_names, total_pages = await get_models(client, httpx.BasicAuth("key", "secret"), 1)

    assert user_model_names == {"meta.llama3-1-8b-instruct-v1:0"}
    assert total_pages == 1
    mock_get.assert_called_once()


async def test_add_model_success(mocker: MockFixture) -> None:
    mock_post = mocker.patch(
        "httpx.AsyncClient.post",
        return_value=AsyncMock(json=Mock(return_value={}), raise_for_status=Mock(return_value=None)),
    )
    client = httpx.AsyncClient()

    model_name = "meta.llama3-1-8b-instruct-v1:0"
    auth = httpx.BasicAuth("key", "secret")
    await add_model(model_name, client, auth)

    mock_post.assert_called_once_with(
        f"{settings.langfuse_host}/api/public/models",
        auth=auth,
        headers={"Content-Type": "application/json"},
        json=USER_MODELS[model_name],
    )


async def test_setup_langfuse_prices(mocker: MockFixture) -> None:
    mock_get_models = mocker.patch("app.langfuse_bedrock.get_models", return_value=({"existing_model"}, 2))
    mock_add_model = mocker.patch("app.langfuse_bedrock.add_model", return_value=None)

    await setup_langfuse_prices()

    assert mock_get_models.call_count == 2
    # Assert that missing models were added
    expected_models_to_add = USER_MODELS.keys() - {"existing_model"}
    assert mock_add_model.call_count == len(expected_models_to_add)
