import asyncio

import httpx

from app.settings import settings

# Prices from https://aws.amazon.com/de/bedrock/pricing/
USER_MODELS = {
    "meta.llama3-8b-instruct-v1:0": {
        "modelName": "meta.llama3-8b-instruct-v1:0",
        "matchPattern": r"(?i)^(meta.llama3-8b-instruct-v1:0)$",
        "unit": "TOKENS",
        "inputPrice": 0.0000003,
        "outputPrice": 0.0000006,
    },
    "meta.llama3-70b-instruct-v1:0": {
        "modelName": "meta.llama3-70b-instruct-v1:0",
        "matchPattern": r"(?i)^(meta.llama3-70b-instruct-v1:0)$",
        "unit": "TOKENS",
        "inputPrice": 0.00000265,
        "outputPrice": 0.0000035,
    },
    "meta.llama3-1-8b-instruct-v1:0": {
        "modelName": "meta.llama3-1-8b-instruct-v1:0",
        "matchPattern": r"(?i)^(meta.llama3-1-8b-instruct-v1:0)$",
        "unit": "TOKENS",
        "inputPrice": 0.00000022,
        "outputPrice": 0.00000022,
    },
    "meta.llama3-1-70b-instruct-v1:0": {
        "modelName": "meta.llama3-1-70b-instruct-v1:0",
        "matchPattern": r"(?i)^(meta.llama3-1-70b-instruct-v1:0)$",
        "unit": "TOKENS",
        "inputPrice": 0.00000099,
        "outputPrice": 0.00000099,
    },
    "meta.llama3-1-405b-instruct-v1:0": {
        "modelName": "meta.llama3-1-405b-instruct-v1:0",
        "matchPattern": r"(?i)^(meta.llama3-1-405b-instruct-v1:0)$",
        "unit": "TOKENS",
        "inputPrice": 0.00000532,
        "outputPrice": 0.000016,
    },
    "meta.llama3-2-3b-instruct-v1:0": {
        "modelName": "meta.llama3-2-3b-instruct-v1:0",
        "matchPattern": r"(?i)^(us|eu)\.(meta.llama3-2-3b-instruct-v1:0)$",
        "unit": "TOKENS",
        "inputPrice": 0.00000017,
        "outputPrice": 0.00000017,
    },
    "meta.llama3-2-1b-instruct-v1:0": {
        "modelName": "meta.llama3-2-1b-instruct-v1:0",
        "matchPattern": r"(?i)^(us|eu)\.(meta.llama3-2-1b-instruct-v1:0)$",
        "unit": "TOKENS",
        "inputPrice": 0.00000011,
        "outputPrice": 0.00000011,
    },
    "claude-3-sonnet-20240229": {
        "modelName": "claude-3-sonnet-20240229",
        "matchPattern": r"(?i)^(us|eu)\.(anthropic.claude-3-sonnet-20240229-v1:0)$",
        "tokenizerId": "claude",
        "tokenizerConfig": {},
        "unit": "TOKENS",
        "inputPrice": 0.000003,
        "outputPrice": 0.000015,
    },
    "claude-3-haiku-20240307": {
        "modelName": "claude-3-haiku-20240307",
        "matchPattern": r"(?i)^(us|eu)\.(anthropic.claude-3-haiku-20240307-v1:0)$",
        "tokenizerId": "claude",
        "tokenizerConfig": {},
        "unit": "TOKENS",
        "inputPrice": 0.00000125,
        "outputPrice": 0.00000125,
    },
    "claude-3-5-sonnet-20240620": {
        "modelName": "claude-3-5-sonnet-20240620",
        "matchPattern": r"(?i)^(us|eu)\.(anthropic.claude-3-5-sonnet-20240620-v1:0)$",
        "tokenizerId": "claude",
        "tokenizerConfig": {},
        "unit": "TOKENS",
        "inputPrice": 0.000003,
        "outputPrice": 0.000015,
    },
}


async def get_models(client: httpx.AsyncClient, auth: httpx.Auth, page: int) -> tuple[set[str], int]:
    r = await client.get(
        settings.langfuse_host + "/api/public/models",
        auth=auth,
        params={"limit": 100, "page": page},
    )
    r.raise_for_status()
    data = r.json()
    return {model["modelName"] for model in data["data"] if not model["isLangfuseManaged"]}, data["meta"]["totalPages"]


async def add_model(model_name: str, client: httpx.AsyncClient, auth: httpx.Auth) -> None:
    print("adding user model", model_name)
    r = await client.post(
        settings.langfuse_host + "/api/public/models",
        auth=auth,
        headers={"Content-Type": "application/json"},
        json=USER_MODELS[model_name],
    )
    r.raise_for_status()


async def setup_langfuse_prices() -> None:
    async with httpx.AsyncClient() as client:
        auth = httpx.BasicAuth(
            username=settings.langfuse_public_key, password=settings.langfuse_secret_key.get_secret_value()
        )
        user_model_names, total_pages = await get_models(client, auth, 1)
        if total_pages > 1:
            for model_names, _ in await asyncio.gather(
                *[get_models(client, auth, page) for page in range(2, total_pages + 1)]
            ):
                user_model_names.update(model_names)

        async with asyncio.TaskGroup() as tg:
            for model_name in USER_MODELS.keys() - user_model_names:
                tg.create_task(add_model(model_name, client, auth))
