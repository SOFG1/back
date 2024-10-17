from langchain_core.messages import AIMessage
from langfuse.decorators import langfuse_context

from app.api.models import LLM
from app.engine.spendinglimits import patch_langfuse_handler, spending_limits_callback
from app.settings import settings
from custom_prompts import CONVERSATION_TITLE_PROMPT


def get_conversation_title(last_message: str, llm_option: LLM) -> str:
    prompt = CONVERSATION_TITLE_PROMPT.format(usr_msg=last_message, system_language=settings.system_language)
    langfuse_handler = langfuse_context.get_current_langchain_handler()
    assert langfuse_handler
    llm = settings.title_llm(llm_option=llm_option)
    out = llm.invoke(prompt, config={"callbacks": [patch_langfuse_handler(langfuse_handler), spending_limits_callback]})

    if isinstance(out, AIMessage):
        out = out.content
        assert isinstance(out, str)
    return out[: settings.title_max_length]
