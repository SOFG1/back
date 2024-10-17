from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse

from app.api.exceptions import TooManyRequestsError
from app.api.i18n import ErrorCode


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> ORJSONResponse:  # noqa: ARG001
    err = TooManyRequestsError()
    return ORJSONResponse(
        status_code=err.status_code,
        content={"detail": {"error_code": err.error_code}},
    )


async def standard_validation_exception_handler(request: Request, exc: RequestValidationError) -> ORJSONResponse:  # noqa: ARG001
    return ORJSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder(
            {
                "detail": {
                    "error_code": ErrorCode.VALIDATION_ERROR,
                    "extra": {"errors": exc.errors()},
                }
            }
        ),
    )


async def internal_server_error_handler(request: Request, exc: Exception) -> ORJSONResponse:  # noqa: ARG001
    return ORJSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=jsonable_encoder(
            {
                "detail": {
                    "error_code": ErrorCode.INTERNAL_SERVER_ERRROR,
                    "extra": {"error": str(exc)},
                }
            }
        ),
    )
