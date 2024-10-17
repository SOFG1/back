from collections.abc import Callable, Generator
from functools import wraps
from typing import Any, ParamSpec, Protocol, TypeVar
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, LLMResult
from langfuse.callback.langchain import LangchainCallbackHandler
from sqlalchemy import text
from sqlmodel import select
from typing_extensions import runtime_checkable

from app.api.models import SpendingLimit, SpendingLimitType
from app.api.tools.db import db_engine
from app.custom_logging import get_logger
from app.settings import settings

try:
    from typing import override
except ImportError:
    from typing_extensions import override

logger = get_logger(__name__)


class SpendingLimitExceededError(Exception):
    pass


class SpendingLimitCountingFailedError(Exception):
    pass


@runtime_checkable
class MessageWithUsageMetadata(Protocol):
    usage_metadata: dict[str, Any] | None


class SpendingLimitsCallback(BaseCallbackHandler):
    raise_error = True

    def __init__(self) -> None:
        super().__init__()
        self.logger = get_logger(self.__class__.__name__)

    @staticmethod
    def get_spending_limit(spending_limit_type: SpendingLimitType) -> SpendingLimit:
        with db_engine.get_session_raw() as session:
            budget = session.exec(select(SpendingLimit).where(SpendingLimit.type == spending_limit_type)).first()
            if budget is None:
                initial_value = settings.get_spending_limit(spending_limit_type)
                budget = SpendingLimit(type=spending_limit_type, value=initial_value)
                logger.info("initializing budget %s with a value of %d", spending_limit_type, budget.value)
                session.add(budget)
                session.commit()
                session.refresh(budget)
            assert budget is not None
            assert budget.type == spending_limit_type
            assert budget.value is not None
            return budget

    @staticmethod
    def decrease_spending_limit(spending_limit_type: SpendingLimitType, consumed_value: int) -> None:
        with db_engine.get_session().__next__() as session:
            session.execute(
                text("UPDATE spendinglimit SET value = value - :consumed_value WHERE type = :spending_limit_type"),
                {"consumed_value": consumed_value, "spending_limit_type": spending_limit_type.name},
            )
            session.commit()

    @staticmethod
    def _raise_error_if_spending_budget_exceeded() -> None:
        if SpendingLimitsCallback.get_spending_limit(SpendingLimitType.INPUT_TOKEN).value < 0:
            raise SpendingLimitExceededError
        if SpendingLimitsCallback.get_spending_limit(SpendingLimitType.OUTPUT_TOKEN).value < 0:
            raise SpendingLimitExceededError

    @override
    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._raise_error_if_spending_budget_exceeded()

    @override
    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._raise_error_if_spending_budget_exceeded()

    def _extract_usage(self, response: LLMResult) -> Generator[tuple[int | None, int | None]]:
        for x in response.generations:
            assert len(x) > 0
            for generation in x:
                if (
                    generation.generation_info is not None
                    and "model" in generation.generation_info
                    and "llama" in generation.generation_info["model"]
                ):
                    # local llama3 or llama3.1
                    self.logger.info("using ollama way of counting tokens")
                    yield (
                        generation.generation_info.get("prompt_eval_count"),
                        generation.generation_info.get("eval_count"),
                    )
                elif isinstance(generation, ChatGeneration | ChatGenerationChunk) and generation.message is not None:
                    if (
                        isinstance(generation.message, MessageWithUsageMetadata)
                        and generation.message.usage_metadata is not None
                    ):
                        # OpenAI, Amazon Bedrock us-west-2
                        yield (
                            generation.message.usage_metadata.get("input_tokens"),
                            generation.message.usage_metadata.get("output_tokens"),
                        )
                    elif (
                        generation.message.response_metadata is not None
                        and "amazon-bedrock-invocationMetrics" in generation.message.response_metadata
                    ):
                        # Amazon Bedrock us-west-2 with stop condition
                        yield (
                            generation.message.response_metadata["amazon-bedrock-invocationMetrics"].get(
                                "inputTokenCount"
                            ),
                            generation.message.response_metadata["amazon-bedrock-invocationMetrics"].get(
                                "outputTokenCount"
                            ),
                        )

    @override
    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        input_tokens = 0
        output_tokens = 0
        assert len(response.generations) > 0
        for input_, output in self._extract_usage(response):
            assert input_ is not None
            assert input_ > 0
            input_tokens += input_

            assert output is not None
            assert output > 0
            output_tokens += output
        if input_tokens <= 0 or output_tokens <= 0:
            raise SpendingLimitCountingFailedError(response)
        self.decrease_spending_limit(SpendingLimitType.INPUT_TOKEN, input_tokens)
        self.decrease_spending_limit(SpendingLimitType.OUTPUT_TOKEN, output_tokens)

        self.logger.info("consumed %d input and %d output tokens", input_tokens, output_tokens)


P = ParamSpec("P")
R = TypeVar("R")


def patch_langfuse_handler(langfuse_handler: LangchainCallbackHandler) -> LangchainCallbackHandler:
    """Patch langfuse handler to correctly count Ollama tokens."""
    original_update_trace_and_remove_state = langfuse_handler._update_trace_and_remove_state  # noqa: SLF001

    capture = {}

    @override
    def patched_update_trace_and_remove_state(
        run_id: str,
        parent_run_id: str | None,
        output: Any,
        *,
        keep_state: bool = False,
        **kwargs: Any,
    ) -> None:
        """Defer calling this function, save call arguments."""
        capture[run_id] = {
            "run_id": run_id,
            "parent_run_id": parent_run_id,
            "output": output,
            "keep_state": keep_state,
            "kwargs": kwargs,
        }

    langfuse_handler._update_trace_and_remove_state = patched_update_trace_and_remove_state  # noqa: SLF001

    def call_patched_upate_trace_and_remove_state(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            run_id = kwargs.get("run_id")
            assert run_id is not None
            ret = func(*args, **kwargs)
            orig_args = capture[run_id]
            original_update_trace_and_remove_state(
                run_id=orig_args["run_id"],
                parent_run_id=orig_args["parent_run_id"],
                output=orig_args["output"],
                keep_state=orig_args["keep_state"],
                **orig_args["kwargs"],
            )
            return ret

        return wrapper

    original_on_llm_end = langfuse_handler.on_llm_end

    @override
    def patched_on_llm_end(
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        ret = original_on_llm_end(response, run_id=run_id, parent_run_id=parent_run_id, **kwargs)
        input_tokens = 0
        output_tokens = 0
        for x in response.generations:
            for generation in x:
                try:
                    if (
                        generation.generation_info is not None
                        and "model" in generation.generation_info
                        and "llama" in generation.generation_info["model"]
                    ):
                        # lokal llama3 or llama3.1
                        input_ = generation.generation_info["prompt_eval_count"]
                        assert input_ is not None
                        assert input_ > 0
                        output = generation.generation_info["eval_count"]
                        assert output is not None
                        assert output > 0
                        input_tokens += input_
                        output_tokens += output
                except Exception:  # noqa: S110
                    pass
        if input_tokens > 0 and output_tokens > 0:
            langfuse_handler.runs[run_id].update(
                usage={
                    "input": input_tokens,
                    "output": output_tokens,
                    "unit": "TOKENS",
                    "inputCost": 0,
                    "outputCost": 0,
                }
            )
        return ret

    # All span ending functions need to call the deferred function
    langfuse_handler.on_llm_end = call_patched_upate_trace_and_remove_state(patched_on_llm_end)
    langfuse_handler.on_agent_finish = call_patched_upate_trace_and_remove_state(langfuse_handler.on_agent_finish)
    langfuse_handler.on_chain_end = call_patched_upate_trace_and_remove_state(langfuse_handler.on_chain_end)
    langfuse_handler.on_chain_error = call_patched_upate_trace_and_remove_state(langfuse_handler.on_chain_error)
    langfuse_handler.on_retriever_end = call_patched_upate_trace_and_remove_state(langfuse_handler.on_retriever_end)
    langfuse_handler.on_tool_end = call_patched_upate_trace_and_remove_state(langfuse_handler.on_tool_end)
    langfuse_handler.on_tool_error = call_patched_upate_trace_and_remove_state(langfuse_handler.on_tool_error)
    langfuse_handler.on_llm_error = call_patched_upate_trace_and_remove_state(langfuse_handler.on_llm_error)

    return langfuse_handler


spending_limits_callback = SpendingLimitsCallback()
