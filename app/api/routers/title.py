from typing import Annotated

from fastapi import APIRouter, Depends, Response, Security, status
from langfuse.decorators import langfuse_context, observe
from sqlmodel import Session

from app.api.exceptions import (
    ConversationNotFoundError,
    ConversationTitleNotFoundError,
    LLMNotFoundError,
    MessageFromUserExpectedError,
    NoMessagesProvidedError,
    NotAuthorizedError,
)
from app.api.models import (
    LLM,
    Conversation,
    ConversationId,
    ConversationPublic,
    ErrorMessage,
    MessageRole,
    Scope,
    TitleData,
    TitleUpdate,
    User,
)
from app.api.routers.conversation import links
from app.api.tools.auth import get_current_user
from app.api.tools.conversation_title import get_conversation_title
from app.api.tools.db import db_engine
from app.custom_logging import get_logger

title_router = tr = APIRouter(prefix="/api/title", tags=["conversations"])

logger = get_logger(__name__)


def get_conversation_by_id(
    id: ConversationId,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CONVERSATIONS])],
) -> Conversation:
    conversation: Conversation | None = session.get(Conversation, id)
    if not conversation:
        raise ConversationNotFoundError
    if conversation.user.id != user.id:
        raise NotAuthorizedError
    return conversation


@tr.post(
    "/{id}",
    status_code=status.HTTP_201_CREATED,
    response_model=ConversationPublic,
    responses={
        status.HTTP_201_CREATED: {"links": {k: v for k, v in links.items() if k != "POST /api/title/{id}"}},
        status.HTTP_400_BAD_REQUEST: {"model": ErrorMessage},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorMessage},
    },
    deprecated=True,
)
@observe()
def create_title(
    conversation: Annotated[Conversation, Depends(get_conversation_by_id)],
    response: Response,
    data: TitleData,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CONVERSATIONS])],
) -> Conversation:
    langfuse_context.update_current_trace(user_id=str(user.id), session_id=str(conversation.id))

    if conversation.title is not None:
        return conversation

    # Get last user message and create title
    if not conversation.history:
        raise NoMessagesProvidedError
    try:
        last_user_message = next(
            message for message in reversed(conversation.history) if message.role == MessageRole.USER
        )
    except StopIteration as e:
        raise MessageFromUserExpectedError from e
    llm: LLM | None = session.get(LLM, data.llm)
    if llm is None:
        raise LLMNotFoundError
    title = get_conversation_title(last_message=last_user_message.content, llm_option=llm)
    if title:
        conversation.title = title
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        response.status_code = status.HTTP_201_CREATED
        return conversation

    raise ConversationTitleNotFoundError


@tr.patch(
    "/{id}",
    status_code=status.HTTP_200_OK,
    response_model=ConversationPublic,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "PATCH /api/title/{id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
    deprecated=True,
)
def patch_title(
    conversation: Annotated[Conversation, Depends(get_conversation_by_id)],
    title_update: TitleUpdate,
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> Conversation:
    conversation.title = title_update.title
    session.add(conversation)
    session.commit()
    session.refresh(conversation)

    return conversation
