from unittest.mock import patch
from uuid import uuid1, uuid4

import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, Generation, GenerationChunk
from langfuse.callback.langchain import LLMResult

from app.api.models import SpendingLimitType
from app.engine.spendinglimits import (
    SpendingLimitExceededError,
    SpendingLimitsCallback,
)
from app.settings import settings


@pytest.mark.usefixtures("test_app")
def test_spendinglimits() -> None:
    initial_value = settings.spending_limit_input_tokens_initial_value
    SpendingLimitsCallback().on_llm_start({}, [], run_id=uuid1())
    assert (
        SpendingLimitsCallback.get_spending_limit(SpendingLimitType.INPUT_TOKEN).value
        == settings.spending_limit_input_tokens_initial_value
    )

    SpendingLimitsCallback.decrease_spending_limit(SpendingLimitType.INPUT_TOKEN, 1000)
    assert SpendingLimitsCallback.get_spending_limit(SpendingLimitType.INPUT_TOKEN).value == initial_value - 1000
    SpendingLimitsCallback().on_llm_start({}, [], run_id=uuid1())

    SpendingLimitsCallback.decrease_spending_limit(SpendingLimitType.INPUT_TOKEN, 1000)
    assert SpendingLimitsCallback.get_spending_limit(SpendingLimitType.INPUT_TOKEN).value == initial_value - 2000

    SpendingLimitsCallback.decrease_spending_limit(SpendingLimitType.INPUT_TOKEN, 10_000_000)
    assert SpendingLimitsCallback.get_spending_limit(SpendingLimitType.INPUT_TOKEN).value == initial_value - 10_002_000
    with pytest.raises(SpendingLimitExceededError):
        SpendingLimitsCallback().on_llm_start({}, [], run_id=uuid1())


test_cases = [
    (
        "openai",
        [
            [
                ChatGenerationChunk(
                    text="...",
                    generation_info={
                        "finish_reason": "stop",
                        "model_name": "gpt-4o-mini-2024-07-18",
                        "system_fingerprint": "fp_483d39d857",
                    },
                    message=AIMessageChunk(
                        content="...",
                        response_metadata={
                            "finish_reason": "stop",
                            "model_name": "gpt-4o-mini-2024-07-18",
                            "system_fingerprint": "fp_483d39d857",
                        },
                        id="run-62c82b60-736d-4f3d-bce5-f5e3a6be97a5",
                        usage_metadata={"input_tokens": 937, "output_tokens": 306, "total_tokens": 1243},
                    ),
                )
            ]
        ],
        937,
        306,
    ),
    (
        "bedrock",
        [
            [
                ChatGenerationChunk(
                    text="...",
                    message=AIMessageChunk(
                        content="...",
                        response_metadata={"stop_reason": None},
                        id="run-c1ca6642-5bca-4bf9-b21e-898b8444c812",
                        usage_metadata={"input_tokens": 1022, "output_tokens": 289, "total_tokens": 1311},
                    ),
                )
            ]
        ],
        1022,
        289,
    ),
    (
        "bedrock_stopped",
        [
            [
                ChatGenerationChunk(
                    text="...",
                    message=AIMessageChunk(
                        content="...",
                        response_metadata={
                            "stop_reason": "length",
                            "amazon-bedrock-invocationMetrics": {
                                "inputTokenCount": 1022,
                                "outputTokenCount": 200,
                                "invocationLatency": 6553,
                                "firstByteLatency": 307,
                            },
                        },
                        id="run-fc00d0d4-835c-4393-9f98-d0bc7f8cb08e",
                    ),
                )
            ]
        ],
        1022,
        200,
    ),
    (
        "llama3_1_local",
        [
            [
                GenerationChunk(
                    text="...",
                    generation_info={
                        "model": "llama3.1:70b",
                        "created_at": "2024-09-13T17:00:42.172217168Z",
                        "response": "",
                        "done": True,
                        "done_reason": "stop",
                        "context": [0],
                        "total_duration": 144280382010,
                        "load_duration": 15436497,
                        "prompt_eval_count": 1019,
                        "prompt_eval_duration": 5650424000,
                        "eval_count": 348,
                        "eval_duration": 138573527000,
                    },
                )
            ]
        ],
        1019,
        348,
    ),
]


@pytest.mark.parametrize(("test_name", "generations", "expected_input_tokens", "expected_output_tokens"), test_cases)
def test_spending_limits_decrement(
    test_name: str,  # noqa: ARG001
    generations: list[list[Generation]],
    expected_input_tokens: int,
    expected_output_tokens: int,
) -> None:
    # Create an instance of SpendingLimitsCallback
    callback = SpendingLimitsCallback()

    # Mock the decrease_spending_limit method
    with patch.object(callback, "decrease_spending_limit") as mock_decrease:
        response = LLMResult(generations=generations)
        callback.on_llm_end(response, run_id=uuid4())

        # Verify that decrease_spending_limit was called with the correct parameters
        mock_decrease.assert_any_call(SpendingLimitType.INPUT_TOKEN, expected_input_tokens)
        mock_decrease.assert_any_call(SpendingLimitType.OUTPUT_TOKEN, expected_output_tokens)
