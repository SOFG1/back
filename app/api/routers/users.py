from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Security, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.api.exceptions import (
    CantChangeSuperadminPermissionError,
    CantDeleteSuperadminError,
    GroupNotFoundError,
    IncorrectPasswordError,
    InvalidUserProvidedCredentialsError,
    UserExistsError,
    UserNotAuthorizedError,
    UserNotFoundError,
)
from app.api.models import (
    ADMIN_ID,
    ALL_USERS_GROUP_ID,
    Directory,
    ErrorMessage,
    Group,
    GroupPublicWithChatbots,
    ListFilter,
    Scope,
    StatusMessage,
    Token,
    User,
    UserChangeAvatar,
    UserChangeName,
    UserChangePassword,
    UserCreate,
    UserId,
    UserPublicDetailed,
    UserRegister,
    UserSetScopes,
)
from app.api.routers.files import delete_file_with_cleanup
from app.api.tools.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from app.api.tools.db import db_engine
from app.settings import limiter, settings

router = APIRouter(prefix="/api/users", tags=["users"])
links = {
    "GET /api/users/{id}": {
        "operationId": "get_user_api_users__id__get",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "GET /api/users/{id}/groups": {
        "operationId": "get_user_id_groups_api_users__id__groups_get",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "PATCH /api/users/{id}/scopes": {
        "operationId": "user_set_scopes_api_users__id__scopes_patch",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "DELETE /api/users/{id}": {
        "operationId": "delete_user_api_users__id__delete",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "POST /api/groups/{id}/user/{user_id}": {
        "operationId": "add_member_api_groups__id__user__user_id__post",
        "parameters": {"user_id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `user_id` value",
    },
    "DELETE /api/groups/{id}/user/{user_id}": {
        "operationId": "remove_member_api_groups__id__user__user_id__delete",
        "parameters": {"user_id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `user_id` value",
    },
    "POST /api/chatbots/{id}/user/{user_id}": {
        "operationId": "add_user_api_chatbots__id__user__user_id__post",
        "parameters": {"user_id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `user_id` value",
    },
    "DELETE /api/chatbots/{id}/user/{user_id}": {
        "operationId": "remove_user_api_chatbots__id__user__user_id__delete",
        "parameters": {"user_id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `user_id` value",
    },
}


def get_user_by_id(
    id: UserId,
    session: Annotated[Session, Depends(db_engine.get_session)],
    _: Annotated[User, Security(get_current_user, scopes=[Scope.USERS])],
) -> User:
    user: User | None = session.get(User, id)
    if not user:
        raise UserNotFoundError
    return user


def add_user_to_db(session: Session, user_db: User) -> User:
    session.add(user_db)
    try:
        session.commit()
    except IntegrityError as e:
        raise UserExistsError from e
    user_db.root_directory = Directory(name="/", canonical="/", owner_id=user_db.id, owner=user_db)
    all_users_group: Group | None = session.get(Group, ALL_USERS_GROUP_ID)
    if all_users_group is None:
        raise GroupNotFoundError(ALL_USERS_GROUP_ID)
    all_users_group.member.append(user_db)
    all_users_group.modified = datetime.now(tz=UTC)
    session.add_all([user_db, all_users_group])
    session.commit()
    return user_db


def delete_user_files(user: User, session: Session) -> int:
    """Delete all files owned by the user, including cleanup."""
    n_files = len(user.files)
    for file in user.files:
        delete_file_with_cleanup(file, session)
        session.delete(file)
    return n_files


def delete_user_directories(user: User, session: Session) -> int:
    """Delete all directories owned by the user."""
    n_directories = len(user.directories)
    for directory in user.directories:
        session.delete(directory)
    return n_directories


def delete_user_conversations(user: User, session: Session) -> tuple[int, int]:
    """Delete all conversations and messages related to the user."""
    n_conversations = len(user.conversations)
    n_messages = 0
    for conversation in user.conversations:
        for message in conversation.history:
            n_messages += 1
            session.delete(message)
        session.delete(conversation)
    return n_conversations, n_messages


def delete_user_groups(user: User, session: Session) -> int:
    """Delete all groups owned by the user."""
    n_groups = len(user.owned_groups)
    for group in user.owned_groups:
        session.delete(group)
    return n_groups


def delete_user_chatbots(user: User, session: Session) -> int:
    """Delete or transfer ownership of user's chatbots."""
    n_chatbots = len(user.chatbots)
    admin = session.get(User, ADMIN_ID)
    if not admin:
        raise UserNotFoundError(ADMIN_ID)

    for chatbot in user.chatbots:
        if chatbot.conversations:
            # Soft-delete the chatbot and transfer it to admin if conversations exist
            chatbot.deleted = datetime.now(tz=UTC)
            chatbot.owner_id = ADMIN_ID
            chatbot.owner = admin
            user.chatbots.remove(chatbot)
            session.add(chatbot)
        else:
            session.delete(chatbot)

    return n_chatbots


def check_if_admin(user: User) -> None:
    """Raise an error if the user is the admin."""
    if user.id == ADMIN_ID:
        raise CantDeleteSuperadminError


def get_all_users_group(session: Session) -> Group:
    """Retrieve the 'All Users' group or raise an error if it doesn't exist."""
    all_users_group = session.get(Group, ALL_USERS_GROUP_ID)
    if not all_users_group:
        raise GroupNotFoundError(ALL_USERS_GROUP_ID)
    return all_users_group


def remove_user_from_group(user: User, group: Group, session: Session) -> None:
    """Remove a user from a group and update the group's modification time."""
    group.member.remove(user)
    group.modified = datetime.now(tz=UTC)
    session.add(group)


@router.post(
    "/register",
    response_model=UserPublicDetailed,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"links": links},
        status.HTTP_409_CONFLICT: {"model": ErrorMessage},
    },
)
def register_user(
    *,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: UserRegister,
    _: Annotated[User, Security(get_current_user, scopes=[Scope.USERS])],
) -> User:
    """Register a new user."""
    hashed_password = get_password_hash(user.password.get_secret_value())

    return add_user_to_db(
        session,
        User(
            username=user.username,
            name=user.name,
            email=user.email,
            password_hash=hashed_password,
            scopes=",".join(sorted([Scope.CHATBOTS, Scope.CONVERSATIONS, Scope.FILES, Scope.GROUPS])),
            avatar=str(user.avatar),
        ),
    )


@router.post(
    "/token",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorMessage},
    },
)
@limiter.limit(settings.rate_limit)
def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[Session, Depends(db_engine.get_session)],
    request: Request,  # noqa: ARG001
) -> Token:
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise InvalidUserProvidedCredentialsError
    access_token_expires = timedelta(minutes=settings.oauth_token_expire_minutes)
    if set(form_data.scopes) - set(user.scopes.split(",")):
        raise UserNotAuthorizedError
    access_token = create_access_token(
        data={"sub": user.username, "scopes": form_data.scopes},
        expires_delta=access_token_expires,
    )
    return Token(access_token=access_token, token_type="bearer")  # noqa: S106


@router.post(
    "",
    response_model=UserPublicDetailed,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"links": links},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_409_CONFLICT: {"model": ErrorMessage},
    },
)
def create_user(
    *,
    user: UserCreate,
    session: Annotated[Session, Depends(db_engine.get_session)],
    _: Annotated[User, Security(get_current_user, scopes=[Scope.USERS])],
) -> User:
    """Create a new user."""
    hashed_password = get_password_hash(user.password.get_secret_value())
    return add_user_to_db(
        session,
        User(
            username=user.username,
            name=user.name,
            email=user.email,
            password_hash=hashed_password,
            scopes=",".join(sorted(user.scopes)),
            avatar=str(user.avatar),
        ),
    )


@router.get(
    "",
    response_model=list[UserPublicDetailed],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
    },
)
def get_users(
    *,
    list_filter: Annotated[ListFilter, Query()],
    session: Annotated[Session, Depends(db_engine.get_session)],
    _: Annotated[User, Security(get_current_user)],
) -> list[User]:
    """Get a list of all users, newest first.

    Offset and limit can be controlled for pagination.
    """
    users = session.exec(
        select(User).order_by(col(User.modified).desc()).offset(list_filter.offset).limit(list_filter.limit)
    ).all()
    return list(users)


@router.get(
    "/profile",
    response_model=UserPublicDetailed,
    responses={
        status.HTTP_200_OK: {"links": links},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def get_logged_in_user(
    *,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user)],
) -> User:
    """Get the currently logged in user."""
    return session.merge(user, load=False)


@router.get(
    "/groups",
    response_model=list[GroupPublicWithChatbots],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def get_user_groups(
    *,
    list_filter: Annotated[ListFilter, Query()],
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user)],
) -> list[Group]:
    """Get a list of all groups the user is a member in.

    Offset and limit can be controlled for pagination.
    """
    return _groups_query(
        list_filter=list_filter,
        session=session,
        user=user,
    )


def _groups_query(list_filter: ListFilter, session: Session, user: User) -> list[Group]:
    groups = session.exec(
        select(Group)
        .where(col(Group.member).contains(user))
        .order_by(col(Group.modified).desc())
        .offset(list_filter.offset)
        .limit(list_filter.limit),
    ).all()
    return list(groups)


@router.post(
    "/change-password",
    response_model=UserPublicDetailed,
    responses={
        status.HTTP_200_OK: {"links": links},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def user_change_password(
    *,
    passwords: UserChangePassword,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user)],
) -> User:
    """Change the current user's password."""
    if not verify_password(passwords.old_password.get_secret_value(), user.password_hash):
        raise IncorrectPasswordError
    user.password_hash = get_password_hash(passwords.new_password.get_secret_value())
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post(
    "/change-avatar",
    response_model=UserPublicDetailed,
    responses={
        status.HTTP_200_OK: {"links": links},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def user_change_avatar(
    *,
    user_avatar: UserChangeAvatar,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user)],
) -> User:
    """Change the current user's avatar."""
    user.avatar = str(user_avatar.avatar)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post(
    "/change-name",
    responses={
        status.HTTP_200_OK: {"links": links},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
    },
)
def user_change_name(
    *,
    name: UserChangeName,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user)],
) -> User:
    """Change the current user's name."""
    user.name = name.name
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.get(
    "/{id}",
    response_model=UserPublicDetailed,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "GET /api/users/{id}/profile"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def get_user(
    *,
    user: Annotated[User, Depends(get_user_by_id)],
) -> User:
    """Get a user."""
    return user


@router.get(
    "/{id}/groups",
    response_model=list[GroupPublicWithChatbots],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def get_user_id_groups(
    *,
    list_filter: Annotated[ListFilter, Query()],
    user: Annotated[User, Depends(get_user_by_id)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> list[Group]:
    """Get a list of all groups the user is a member in.

    Offset and limit can be controlled for pagination.
    """
    return _groups_query(
        list_filter=list_filter,
        session=session,
        user=user,
    )


@router.patch(
    "/{id}/scopes",
    response_model=UserPublicDetailed,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "PATCH /api/users/{id}/scopes"}},
        status.HTTP_400_BAD_REQUEST: {"model": ErrorMessage},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def user_set_scopes(
    *,
    user: Annotated[User, Depends(get_user_by_id)],
    user_scopes: UserSetScopes,
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> User:
    """Set a users permissions."""
    if user.id == ADMIN_ID and user_scopes.scopes != {"*"}:
        raise CantChangeSuperadminPermissionError
    user.scopes = ",".join(sorted(user_scopes.scopes))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.delete(
    "/{id}",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def delete_user(
    *,
    user: Annotated[User, Depends(get_user_by_id)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> StatusMessage:
    """Delete a user."""

    # Check if the user is the admin, and raise an error if so
    check_if_admin(user)

    # Retrieve the "All Users" group from the database, or raise an error if not found
    all_users_group = get_all_users_group(session)

    # Remove the user from the "All Users" group and update the group's modification time
    remove_user_from_group(user, all_users_group, session)

    # Delete related data
    n_files = delete_user_files(user, session)
    n_directories = delete_user_directories(user, session)
    n_conversations, n_messages = delete_user_conversations(user, session)
    n_groups = delete_user_groups(user, session)
    n_chatbots = delete_user_chatbots(user, session)

    # Actually delete the user
    session.delete(user)
    session.commit()

    return StatusMessage(
        ok=True,
        message=(
            f"Deleted user {user.username}, which had {n_files} file(s), {n_directories} directory(s), "
            f"{n_conversations} conversation(s), {n_messages} message(s), {n_groups} group(s) "
            f"and {n_chatbots} chatbot(s)"
        ),
    )
