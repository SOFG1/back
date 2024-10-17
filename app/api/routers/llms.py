from collections.abc import Sequence
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Security,
)
from sqlmodel import Session, select

from app.api.models import (
    LLM,
    LLMPublic,
    User,
)
from app.api.tools.auth import get_current_user
from app.api.tools.db import db_engine
from app.custom_logging import get_logger

logger = get_logger(__name__)

lr = llms_router = APIRouter(prefix="/api/llms", tags=["llms"])


@lr.get(
    "",
    response_model=list[LLMPublic],
)
def get_llms(
    session: Annotated[Session, Depends(db_engine.get_session)],
    _: Annotated[User, Security(get_current_user, scopes=[])],
) -> Sequence[LLM]:
    return session.exec(select(LLM)).all()
