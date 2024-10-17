from fastapi import status
from fastapi.testclient import TestClient

from app.api.models import LLM, LLMProvider
from app.api.tools.db import db_engine


def test_llms(test_app: TestClient, test_token: str) -> None:
    _id = None
    display_name = "Test"
    provider = LLMProvider.BEDROCK
    llm_model_name = "Test Model"
    title_model_name = "Test Title Model"
    temperature = 0.12
    title_temperature = 0.14
    max_tokens = 4000
    top_p = 0.2
    context_length = 42
    llm = LLM(
        display_name=display_name,
        provider=provider,
        llm_model_name=llm_model_name,
        title_model_name=title_model_name,
        temperature=temperature,
        title_temperature=title_temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        context_length=context_length,
    )
    _id = llm.id
    with db_engine.get_session().__next__() as session:
        session.add(llm)
        session.commit()
    resp = test_app.get(
        "/api/llms",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert resp.status_code == status.HTTP_200_OK, resp.json()
    json = resp.json()
    assert len(json) == 1
    assert json[0]["id"] == str(_id)
    assert json[0]["display_name"] == display_name
