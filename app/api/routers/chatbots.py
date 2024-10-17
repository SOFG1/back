from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Security,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, or_, select

from app.api.exceptions import (
    ChatbotAlreadyOwnedError,
    ChatbotNotFoundError,
    ChatbotSharedGroupError,
    ChatbotSharedUserError,
    FileSInvalidStatusError,
    FileSLinkedToChatbotError,
    FileSNotFoundError,
    GroupNotFoundError,
    NotAuthorizedError,
    UserNotFoundError,
)
from app.api.models import (
    Chatbot,
    ChatbotCreate,
    ChatbotId,
    ChatbotPublicWithFiles,
    ChatbotUpdate,
    ErrorMessage,
    FileId,
    FileUser,
    Group,
    GroupChatbotLink,
    GroupId,
    IndexingStatus,
    ListFilter,
    Scope,
    StatusMessage,
    User,
    UserGroupLink,
    UserId,
    UserSharedLink,
)
from app.api.tools.auth import get_current_user
from app.api.tools.db import db_engine

chatbot_router = cr = APIRouter(prefix="/api/chatbots", tags=["chatbots"])

links = {
    "GET /api/chatbots/{id}": {
        "operationId": "get_chatbot_api_chatbots__id__get",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "POST /api/chatbots/{id}": {
        "operationId": "add_files_api_chatbots__id__post",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "PATCH /api/chatbots/{id}": {
        "operationId": "patch_chatbot_api_chatbots__id__patch",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "DELETE /api/chatbots/{id}": {
        "operationId": "delete_chatbot_api_chatbots__id__delete",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "POST /api/chatbots/{id}/group/{group_id}": {
        "operationId": "add_group_api_chatbots__id__group__group_id__post",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "DELETE /api/chatbots/{id}/group/{group_id}": {
        "operationId": "remove_group_api_chatbots__id__group__group_id__delete",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "POST /api/chatbots/{id}/user/{user_id}": {
        "operationId": "add_user_api_chatbots__id__user__user_id__post",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "DELETE /api/chatbots/{id}/user/{user_id}": {
        "operationId": "remove_user_api_chatbots__id__user__user_id__delete",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "POST /api/conversations": {
        "operationId": "create_conversation_api_conversations_post",
        "requestBody": {"chatbot_id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `chatbot_id` value",
    },
}


# cleaning need to be an extra function and cant be inserted into function "get_chatbot_by_id" or
# equivalent functions because it can only be used for responses (returns). If used at start of endpoint
# the object gets overwritten and that is not the behaviour we want to have.
def clean_chatbot(chatbot: Chatbot) -> Chatbot:
    chatbot.files = [f for f in chatbot.files if not f.expires or f.expires.astimezone(tz=UTC) >= datetime.now(tz=UTC)]
    return chatbot


def get_chatbot_by_id(
    id: ChatbotId,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CHATBOTS])],
) -> Chatbot:
    chatbot: Chatbot | None = session.exec(
        select(Chatbot).where(Chatbot.id == id, col(Chatbot.deleted).is_(None))
    ).one_or_none()
    if chatbot is None:
        raise ChatbotNotFoundError
    if user.id != chatbot.owner_id:
        raise NotAuthorizedError
    return chatbot


def get_chatbot_no_expired_file(
    id: ChatbotId,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CHATBOTS])],
) -> Chatbot:
    return clean_chatbot(get_chatbot_by_id(id, session, user))


def get_user_by_id(user_id: UserId, session: Annotated[Session, Depends(db_engine.get_session)]) -> User:
    user: User | None = session.get(User, user_id)
    if user is None:
        raise UserNotFoundError
    return user


def get_group_by_id(
    group_id: GroupId,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CHATBOTS])],
) -> Group:
    group: Group | None = session.get(Group, group_id)
    if group is None:
        raise GroupNotFoundError
    if user.id not in {m.id for m in group.member}:
        raise NotAuthorizedError
    return group


def check_for_duplicates(chatbot: Chatbot, files: set[FileId]) -> None:
    duplicates = files & {file.id for file in chatbot.files}
    if duplicates:
        raise FileSLinkedToChatbotError([str(id) for id in duplicates])


def validate_files(files: set[FileId], db_files: Sequence[FileUser]) -> None:
    not_found_files = [str(f) for f in files if f not in {df.id for df in db_files}]
    if not_found_files:
        raise FileSNotFoundError(not_found_files)

    invalid_status_files = [str(file.id) for file in db_files if file.file.indexing_status != IndexingStatus.INDEXED]
    if invalid_status_files:
        raise FileSInvalidStatusError(invalid_status_files)


@cr.post(
    "",
    response_model=ChatbotPublicWithFiles,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"links": links},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
        status.HTTP_409_CONFLICT: {"model": ErrorMessage},
    },
)
def create_chatbot(
    *,
    chatbot: ChatbotCreate,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CHATBOTS])],
) -> Chatbot:
    """Create a new chatbot."""
    chatbot_db = Chatbot(
        name=chatbot.name,
        description=chatbot.description,
        system_prompt=chatbot.system_prompt,
        color=chatbot.color.as_named(fallback=True),
        citations_mode=chatbot.citations_mode,
        owner=user,
        owner_id=user.id,
        icon=chatbot.icon,
    )
    if chatbot.files:
        db_files = session.exec(
            select(FileUser).where(
                col(FileUser.id).in_(chatbot.files),
                or_(col(FileUser.expires).is_(None), col(FileUser.expires) >= datetime.now(tz=UTC)),
            )
        ).all()
        if len(db_files) != len(chatbot.files):
            raise FileSNotFoundError([str(f) for f in chatbot.files if f not in {df.id for df in db_files}])
        chatbot_db.files = list(db_files)

    session.add(chatbot_db)
    session.commit()
    session.refresh(chatbot_db)
    return chatbot_db


@cr.get(
    "",
    response_model=list[ChatbotPublicWithFiles],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
    },
)
def get_chatbots(
    *,
    list_filter: Annotated[ListFilter, Query()],
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CHATBOTS])],
) -> list[Chatbot]:
    """Get chatbots owned by the user."""
    chatbots = session.exec(
        select(Chatbot)
        .where(Chatbot.owner_id == user.id, col(Chatbot.deleted).is_(None))
        .order_by(col(Chatbot.modified).desc())
        .offset(list_filter.offset)
        .limit(list_filter.limit)
    ).all()
    return [clean_chatbot(chatbot) for chatbot in chatbots]


@cr.get(
    "/shared",
    response_model=list[ChatbotPublicWithFiles],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
    },
)
def get_shared_chatbots(
    *,
    list_filter: Annotated[ListFilter, Query()],
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CHATBOTS])],
) -> list[Chatbot]:
    """Get all chatbots shared with the user."""
    chatbots = session.exec(
        select(Chatbot)
        .join(UserSharedLink, col(UserSharedLink.chatbot_id) == col(Chatbot.id), isouter=True)
        .join(GroupChatbotLink, col(GroupChatbotLink.chatbot_id) == col(Chatbot.id), isouter=True)
        .join(UserGroupLink, col(UserGroupLink.group_id) == col(GroupChatbotLink.group_id), isouter=True)
        .where(
            Chatbot.owner_id != user.id,
            col(Chatbot.deleted).is_(None),
            or_(
                UserSharedLink.user_id == user.id,  # Directly shared chatbots
                UserGroupLink.user_id == user.id,  # Group-shared chatbots
            ),
        )
        .order_by(col(Chatbot.modified).desc())
        .distinct()
        .offset(list_filter.offset)
        .limit(list_filter.limit)
    ).all()

    return [clean_chatbot(chatbot) for chatbot in chatbots]


@cr.get(
    "/{id}",
    response_model=ChatbotPublicWithFiles,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "GET /api/chatbots/{id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def get_chatbot(
    *,
    chatbot: Annotated[Chatbot, Depends(get_chatbot_no_expired_file)],
) -> Chatbot:
    """Get a chatbot."""
    return chatbot


@cr.post(
    "/{id}",
    response_model=ChatbotPublicWithFiles,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "POST /api/chatbots/{id}"}},
        status.HTTP_400_BAD_REQUEST: {"model": ErrorMessage},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
        status.HTTP_409_CONFLICT: {"model": ErrorMessage},
    },
)
def add_files(
    *,
    chatbot: Annotated[Chatbot, Depends(get_chatbot_by_id)],
    files: set[FileId],
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CHATBOTS])],
) -> Chatbot:
    """Add links to files.
    Note: old links are not removed.
    """
    check_for_duplicates(chatbot, files)
    db_files = session.exec(
        select(FileUser).where(
            FileUser.owner_id == user.id,
            col(FileUser.id).in_(files),
            or_(col(FileUser.expires).is_(None), col(FileUser.expires) >= datetime.now(tz=UTC)),
        )
    ).all()
    validate_files(files, db_files)
    if files:
        chatbot.files.extend(db_files)
        session.add(chatbot)
        session.commit()
        session.refresh(chatbot)
    return clean_chatbot(chatbot)


@cr.patch(
    "/{id}",
    response_model=ChatbotPublicWithFiles,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "PATCH /api/chatbots/{id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
        status.HTTP_409_CONFLICT: {"model": ErrorMessage},
    },
)
def patch_chatbot(
    *,
    chatbot: Annotated[Chatbot, Depends(get_chatbot_by_id)],
    chatbot_update: ChatbotUpdate,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.CHATBOTS])],
) -> Chatbot:
    """Patch a chatbot."""
    chatbot_data = chatbot_update.model_dump(exclude_unset=True, exclude={"files", "color"})
    if chatbot_update.color is not None:
        chatbot_data["color"] = chatbot_update.color.as_named(fallback=True)
    for k, v in chatbot_data.items():
        if v is not None and getattr(chatbot, k) != v:
            setattr(chatbot, k, v)
    if chatbot_update.files is not None:
        files = session.exec(
            select(FileUser).where(
                FileUser.owner_id == user.id,
                col(FileUser.id).in_(chatbot_update.files),
                or_(col(FileUser.expires).is_(None), col(FileUser.expires) >= datetime.now(tz=UTC)),
            )
        ).all()
        chatbot.files = list(files)
        if len(chatbot_update.files) != len(chatbot.files):
            raise FileSNotFoundError([str(f) for f in chatbot_update.files if f not in {df.id for df in chatbot.files}])

    session.add(chatbot)
    session.commit()
    session.refresh(chatbot)
    return clean_chatbot(chatbot)


@cr.delete(
    "/{id}",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def delete_chatbot(
    *,
    chatbot: Annotated[Chatbot, Depends(get_chatbot_by_id)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> StatusMessage:
    """Soft-Delete a chatbot."""
    if chatbot.conversations:
        chatbot.deleted = datetime.now(tz=UTC)
        session.add(chatbot)
    else:
        session.delete(chatbot)
    session.commit()
    return StatusMessage(ok=True, message=f"Deleted chatbot {chatbot.name}")


@cr.post(
    "/{id}/group/{group_id}",
    response_model=ChatbotPublicWithFiles,
    responses={
        status.HTTP_200_OK: {
            "links": {k: v for k, v in links.items() if k != "POST /api/chatbots/{id}}/group/{group_id}"},
        },
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
        status.HTTP_409_CONFLICT: {"model": ErrorMessage},
    },
)
def add_group(
    *,
    chatbot: Annotated[Chatbot, Depends(get_chatbot_by_id)],
    group: Annotated[Group, Depends(get_group_by_id)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> Chatbot:
    chatbot.groups.append(group)
    session.add(chatbot)
    try:
        session.commit()
    except IntegrityError as e:
        raise ChatbotSharedGroupError from e
    session.refresh(chatbot)
    return clean_chatbot(chatbot)


@cr.delete(
    "/{id}/group/{group_id}",
    response_model=ChatbotPublicWithFiles,
    responses={
        status.HTTP_200_OK: {
            "links": {k: v for k, v in links.items() if k != "DELETE /api/chatbots/{id}/group/{group_id}"},
        },
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def remove_group(
    *,
    chatbot: Annotated[Chatbot, Depends(get_chatbot_by_id)],
    group: Annotated[Group, Depends(get_group_by_id)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> Chatbot:
    chatbot.groups.remove(group)
    session.add(chatbot)
    session.commit()
    session.refresh(chatbot)
    return clean_chatbot(chatbot)


@cr.post(
    "/{id}/user/{user_id}",
    response_model=ChatbotPublicWithFiles,
    responses={
        status.HTTP_200_OK: {
            "links": {k: v for k, v in links.items() if k != "PATCH /api/chatbots/{id}/user/{user_id}"},
        },
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
        status.HTTP_409_CONFLICT: {"model": ErrorMessage},
    },
)
def add_user(
    *,
    chatbot: Annotated[Chatbot, Depends(get_chatbot_by_id)],
    user: Annotated[User, Depends(get_user_by_id)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> Chatbot:
    if chatbot.owner_id == user.id:
        raise ChatbotAlreadyOwnedError
    chatbot.individuals.append(user)
    session.add(chatbot)
    try:
        session.commit()
    except IntegrityError as e:
        raise ChatbotSharedUserError from e
    session.refresh(chatbot)
    return clean_chatbot(chatbot)


@cr.delete(
    "/{id}/user/{user_id}",
    response_model=ChatbotPublicWithFiles,
    responses={
        status.HTTP_200_OK: {
            "links": {k: v for k, v in links.items() if k != "DELETE /api/chatbots/{id}/user/{user_id}"},
        },
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def remove_user(
    *,
    chatbot: Annotated[Chatbot, Depends(get_chatbot_by_id)],
    user: Annotated[User, Depends(get_user_by_id)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> Chatbot:
    chatbot.individuals.remove(user)
    session.add(chatbot)
    session.commit()
    session.refresh(chatbot)
    return clean_chatbot(chatbot)
