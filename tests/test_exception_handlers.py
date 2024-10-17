import json
from unittest.mock import Mock

import pytest

from app.api.exception_handlers import rate_limit_exceeded_handler
from app.api.exceptions import TooManyRequestsError


@pytest.mark.asyncio
async def test_rate_limit_exceeded_handler() -> None:
    response = await rate_limit_exceeded_handler(request=Mock(), exc=Mock())

    assert response.status_code == TooManyRequestsError.status_code
    assert isinstance(response.body, bytes)
    assert json.loads(response.body) == {"detail": {"error_code": TooManyRequestsError.error_code}}
