import json
import re
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Security, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langfuse.decorators import langfuse_context, observe
from sqlmodel import Session, col, select

from app.api.exceptions import (
    ChatbotMissingError,
    ChatbotNotFoundError,
    ConversationNotFoundError,
    LLMNotFoundError,
    MessageNotFoundError,
    MessageUpdateError,
    NotAuthorizedError,
)
from app.api.models import (
    LLM,
    Conversation,
    ConversationData,
    ConversationId,
    ConversationMessageLink,
    DBMessage,
    ErrorMessage,
    MessageId,
    MessageRole,
    Scope,
    User,
)
from app.api.routers.users import get_current_user
from app.api.tools.db import db_engine
from app.api.tools.json_formatter import convert_to_json, get_sorted_resource_list
from app.engine.chains import Chains
from app.engine.spendinglimits import patch_langfuse_handler, spending_limits_callback
from app.settings import settings

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableSerializable

chat_router = chat = APIRouter(prefix="/api/chat", tags=["chat"])

MessageClass: dict[MessageRole, type[BaseMessage]] = {
    MessageRole.USER: HumanMessage,
    MessageRole.AI: AIMessage,
}

N_MESSAGES = 10


def get_conversation_by_id(session: Session, conversation_id: ConversationId, user: User) -> Conversation:
    """
    Fetch conversation by ID and ensure the current user is authorized to access it.
    """
    db_conversation = session.get(Conversation, conversation_id)
    if not db_conversation:
        raise ConversationNotFoundError
    if db_conversation.user != user:
        raise NotAuthorizedError
    if not db_conversation.chatbot:
        raise ChatbotMissingError
    if db_conversation.chatbot.deleted:
        raise ChatbotNotFoundError
    return db_conversation


def get_llm(session: Session, llm_id: UUID) -> LLM:
    """
    Fetch the LLM by its ID.
    """
    llm: LLM | None = session.get(LLM, llm_id)
    if llm is None:
        raise LLMNotFoundError
    return llm


def check_last_message(last_message: DBMessage | None, message_id: MessageId) -> None:
    if not last_message:
        raise MessageNotFoundError

    if last_message.id != message_id:
        raise MessageUpdateError


def get_last_message(session: Session, conversation_id: ConversationId, role: MessageRole) -> DBMessage | None:
    """
    Get the last message by role for the specified conversation.
    """
    return session.exec(
        select(DBMessage)
        .join(ConversationMessageLink, col(DBMessage.id) == col(ConversationMessageLink.message_id))
        .where(ConversationMessageLink.conversation_id == conversation_id, DBMessage.role == role)
        .order_by(col(DBMessage.modified).desc())
    ).first()


def clean_message_content(messages: list[DBMessage]) -> list[BaseMessage]:
    """
    Clean up messages and prepare them for processing.
    """
    return [MessageClass[m.role](content=re.sub(r"\[\d+\]", "", m.content)) for m in messages]


async def stream_response(
    request: Request,
    response: AsyncIterator,
    ai_message: DBMessage | None,
    session: Session,
    trace_id: str,
    observation_id: str,
    db_conversation: Conversation,
    citation_mode: bool,  # noqa: FBT001
) -> AsyncGenerator[str, None]:
    """
    Generic response streaming function, handles both message creation and AI response.
    """
    ai_msg = ""
    sources = []
    # use time when response streaming started as created timestamp
    created = datetime.now(UTC)
    # Stream response chunks from LLM
    async for chunk in response:
        if await request.is_disconnected():
            break
        if "sources" in chunk:
            sources.extend(chunk["sources"])
        if "output" in chunk:
            ai_msg += chunk["output"]
            yield f"data: {json.dumps(chunk['output'])}\n\n"

    if citation_mode:
        sources_json = convert_to_json(sources)
        assert sources_json is not None
        yield f"event: context\ndata: {sources_json}\n\n"

    # Update or create AI message
    if ai_message:
        ai_message.content = ai_msg
        ai_message.citations = get_sorted_resource_list(sources)
    else:
        ai_message = DBMessage(
            role=MessageRole.AI,
            content=ai_msg,
            citations=get_sorted_resource_list(sources),
            trace_id=trace_id,
            observation_id=observation_id,
            created=created,
            conversation=db_conversation,
        )
    session.add(ai_message)

    session.commit()
    session.refresh(ai_message)

    metadata = {
        "message_id": str(ai_message.id),
        "trace_id": trace_id,
        "observation_id": observation_id,
        "created": created.isoformat(),
    }

    yield f"event: metadata\ndata: {json.dumps(metadata)}\n\n"


def prepare_llm_response(
    session: Session,
    llm_id: UUID,
    db_conversation: Conversation,
    data: ConversationData,
) -> AsyncIterator:
    # Fetch the LLM by its ID
    llm = get_llm(session, llm_id)

    # Initialize chain for chatbot interactions
    chains = Chains(
        llm=settings.llm(llm),
        session=session,
        chatbot_owner_id=db_conversation.chatbot.owner_id,
    )

    # Get the chain for the current conversation
    conversational_chain: RunnableSerializable = chains.get_conversational_chain(settings, db_conversation)

    # Clean and convert message history for the LLM
    messages = clean_message_content(db_conversation.history)

    # Prepare the response from the conversational chain
    langfuse_handler = langfuse_context.get_current_langchain_handler()
    assert langfuse_handler
    return conversational_chain.astream(
        {
            "question": data.message,
            "chat_history": messages,
            "date": datetime.now().astimezone().isoformat(),
            "chatbot_name": db_conversation.chatbot.name,
        },
        config={
            "callbacks": [
                patch_langfuse_handler(langfuse_handler),
                spending_limits_callback,
            ]
        },
    )


@chat.post(
    "/{conversation_id}",
    response_class=StreamingResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorMessage},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
@observe()
def conversation(
    request: Request,
    conversation_id: ConversationId,
    data: ConversationData,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CONVERSATIONS])],
) -> StreamingResponse:
    """
    Create a conversation and handle user messages and AI responses.
    """
    langfuse_context.update_current_trace(user_id=str(user.id), session_id=str(conversation_id))

    # Fetch conversation and LLM
    db_conversation = get_conversation_by_id(session, conversation_id, user)

    # Initialize chain for chatbot interactions
    response = prepare_llm_response(session=session, llm_id=data.llm, db_conversation=db_conversation, data=data)

    # Save the user's message to the database
    db_message = DBMessage(role=MessageRole.USER, content=data.message, conversation=db_conversation)
    session.add(db_message)
    session.commit()

    # Return the StreamingResponse with the wrapped async iterator
    return StreamingResponse(
        stream_response(
            request=request,
            response=response,
            ai_message=None,
            session=session,
            trace_id=str(langfuse_context.get_current_trace_id()),
            observation_id=str(langfuse_context.get_current_observation_id()),
            db_conversation=db_conversation,
            citation_mode=db_conversation.chatbot.citations_mode
            if db_conversation.citation_mode is None
            else db_conversation.citation_mode,
        ),
        media_type="text/event-stream",
    )


@chat.patch("/{conversation_id}/{message_id}", response_class=StreamingResponse)
@observe()
def edit_last_message(
    request: Request,
    conversation_id: ConversationId,
    message_id: MessageId,
    data: ConversationData,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CONVERSATIONS])],
) -> StreamingResponse:
    """
    Edit the last message in a conversation and regenerate an AI response.
    """
    langfuse_context.update_current_trace(user_id=str(user.id), session_id=str(conversation_id))

    # Fetch the conversation and LLM
    db_conversation = get_conversation_by_id(session, conversation_id, user)
    last_message = get_last_message(session, conversation_id, MessageRole.USER)
    ai_message = get_last_message(session, conversation_id, MessageRole.AI)

    # Validate that the message to edit is the last user message
    check_last_message(last_message, message_id)
    assert last_message  # validated in above function

    # Update last user message
    last_message.content = data.message
    session.add(last_message)
    session.commit()

    # Initialize chain for chatbot interactions
    response = prepare_llm_response(session=session, llm_id=data.llm, db_conversation=db_conversation, data=data)

    # Stream the updated AI response
    return StreamingResponse(
        stream_response(
            request=request,
            response=response,
            ai_message=ai_message,
            session=session,
            trace_id=str(langfuse_context.get_current_trace_id()),
            observation_id=str(langfuse_context.get_current_observation_id()),
            db_conversation=db_conversation,
            citation_mode=db_conversation.citation_mode or db_conversation.chatbot.citations_mode,
        ),
        media_type="text/event-stream",
    )
