from unittest.mock import Mock

from langchain_core.messages import AIMessage
from pytest_mock import MockerFixture

from app.api.tools.conversation_title import get_conversation_title
from app.settings import settings


def test_get_conversation_title(mocker: MockerFixture) -> None:
    langfuse_handler = mocker.patch("app.api.tools.conversation_title.langfuse_context")
    llm_mock = mocker.patch("app.settings.Settings.title_llm")
    llm_mock().invoke.return_value = AIMessage("Mocked Text")

    output = get_conversation_title(last_message="Hello World", llm_option=Mock())
    assert output == "Mocked Text"
    langfuse_handler.get_current_langchain_handler.assert_called_once()

    llm_call_args = llm_mock().invoke.call_args_list[0].args
    llm_call_kwargs = llm_mock().invoke.call_args_list[0].kwargs
    assert llm_call_args[0].startswith("Allways perform the below task using the German language")
    assert len(llm_call_kwargs["config"]["callbacks"]) == 2

    settings.title_max_length = 3
    output = get_conversation_title(last_message="Hello World", llm_option=Mock())
    assert output == "Moc"
