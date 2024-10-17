from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security, status
from fastapi.responses import Response
from langfuse import Langfuse
from langfuse.decorators import langfuse_context, observe
from sqlmodel import Session, col, select

from app.api.exceptions import (
    ChatbotNotFoundError,
    ConversationNotFoundError,
    ConversationTitleNotFoundError,
    LLMNotFoundError,
    MessageFromUserExpectedError,
    MessageNotFoundError,
    NoMessagesProvidedError,
    NotAuthorizedError,
    RateOnlyAIMessagesError,
)
from app.api.models import (
    LLM,
    Chatbot,
    Conversation,
    ConversationCreate,
    ConversationId,
    ConversationPublic,
    ConversationPublicHistory,
    DBMessage,
    ErrorMessage,
    Feedback,
    ListFilter,
    MessageId,
    MessageRole,
    Scope,
    StatusMessage,
    TitleData,
    TitleUpdate,
    User,
)
from app.api.tools.auth import get_current_user
from app.api.tools.conversation_title import get_conversation_title
from app.api.tools.db import db_engine

conversation_router = cr = APIRouter(prefix="/api/conversations", tags=["conversations"])

links = {
    "GET /api/conversations/{id}": {
        "operationId": "get_single_conversation_api_conversations__id__get",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "DELETE /api/conversations/{id}": {
        "operationId": "delete_conversation_api_conversations__id__delete",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "POST /api/conversations/{id}/title": {
        "operationId": "create_title_api_conversations__id__title_post",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "PATCH /api/conversations/{id}/title": {
        "operationId": "patch_title_api_conversations__id__title_patch",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "POST /api/conversations/{id}/feedback/{message_id}": {
        "operationId": "feedback_api_conversations__id__feedback__message_id__post",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "POST /api/chat/{conversation_id}": {
        "operationId": "conversation_api_chat__conversation_id__post",
        "parameters": {"conversation_id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
}


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


def get_message_by_id(message_id: MessageId, session: Annotated[Session, Depends(db_engine.get_session)]) -> DBMessage:
    message: DBMessage | None = session.get(DBMessage, message_id)
    if message is None:
        raise MessageNotFoundError
    return message


@cr.get(
    "",
    response_model=list[ConversationPublic],
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorMessage},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def get_all_conversations(
    list_filter: Annotated[ListFilter, Query()],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CONVERSATIONS])],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> list[Conversation]:
    conversations_query = (
        select(Conversation)
        .where(Conversation.owner_id == user.id)
        .order_by(col(Conversation.modified).desc())
        .offset(list_filter.offset)
        .limit(list_filter.limit)
    )
    return list(session.exec(conversations_query).all())


@cr.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ConversationPublic,
    responses={
        status.HTTP_201_CREATED: {"links": links},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def create_conversation(
    conversation: ConversationCreate,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CONVERSATIONS])],
) -> Conversation:
    # check existing Chatbot
    chatbot: Chatbot | None = session.exec(
        select(Chatbot).where(Chatbot.id == conversation.chatbot_id, col(Chatbot.deleted).is_(None))
    ).one_or_none()
    if not chatbot:
        raise ChatbotNotFoundError
    if (
        chatbot.owner_id != user.id
        and user.id not in {u.id for u in chatbot.individuals}
        and user.id not in {m.id for group in chatbot.groups for m in group.member}
    ):
        raise NotAuthorizedError

    # add user to current session, so it can be added to the conversation
    user = session.merge(user, load=False)
    # create a new conversation with empty history in DB
    conversation_db = Conversation(
        history=[], chatbot=chatbot, user=user, owner_id=user.id, title=None, citation_mode=chatbot.citations_mode
    )
    session.add(conversation_db)
    session.commit()
    session.refresh(conversation_db)
    return conversation_db


@cr.get(
    "/{id}",
    response_model=ConversationPublicHistory,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "GET /api/conversations/{id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def get_single_conversation(
    conversation: Annotated[Conversation, Depends(get_conversation_by_id)],
) -> Conversation:
    return conversation


@cr.post(
    "/{id}/feedback/{message_id}",
    response_model=StatusMessage,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorMessage},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorMessage},
    },
)
def feedback(
    *,
    feedback: Feedback,
    conversation: Annotated[Conversation, Depends(get_conversation_by_id)],
    message: Annotated[DBMessage, Depends(get_message_by_id)],
    session: Annotated[Session, Depends(db_engine.get_session)],
    _user: Annotated[User, Security(get_current_user, scopes=[Scope.CONVERSATIONS])],
) -> StatusMessage:
    if message.role != MessageRole.AI:
        raise RateOnlyAIMessagesError
    if message not in conversation.history:
        raise MessageNotFoundError

    langfuse_client = Langfuse()
    langfuse_client.score(
        trace_id=message.trace_id,
        observation_id=message.observation_id,
        name=feedback.name,
        value=feedback.value,
        comment=feedback.comment,
        data_type="NUMERIC",
    )
    message.feedback_value = feedback.value
    session.add(message)
    session.commit()
    return StatusMessage(ok=True, message="Thank you for your feedback.")


@cr.post(
    "/{id}/title",
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
    title = get_conversation_title(last_user_message.content, llm_option=llm)
    if title:
        conversation.title = title
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        response.status_code = status.HTTP_201_CREATED
        return conversation

    raise ConversationTitleNotFoundError


@cr.patch(
    "/{id}/title",
    status_code=status.HTTP_200_OK,
    response_model=ConversationPublic,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "PATCH /api/title/{id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
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


@cr.delete(
    "/{id}",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def delete_conversation(
    conversation: Annotated[Conversation, Depends(get_conversation_by_id)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> StatusMessage:
    for message in conversation.history:
        session.delete(message)
    chatbot = conversation.chatbot
    if chatbot.deleted and len(chatbot.conversations) == 1:
        session.delete(chatbot)
    session.delete(conversation)
    session.commit()
    return StatusMessage(message=f"Deleted conversation {conversation.id}", ok=True)
