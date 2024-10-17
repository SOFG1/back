from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.api.exceptions import (
    GroupModificationError,
    GroupNotFoundError,
    GroupRemoveError,
    NotAuthorizedError,
    UserInGroupError,
    UserNotFoundError,
)
from app.api.models import (
    ALL_USERS_GROUP_ID,
    ErrorMessage,
    Group,
    GroupCreate,
    GroupId,
    GroupPublic,
    GroupPublicWithChatbots,
    GroupUpdate,
    ListFilter,
    Scope,
    StatusMessage,
    User,
    UserId,
)
from app.api.tools.auth import get_current_user
from app.api.tools.db import db_engine

group_router = gr = APIRouter(prefix="/api/groups", tags=["groups"])

links = {
    "GET /api/groups/{id}": {
        "operationId": "get_group_api_groups__id__get",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "PATCH /api/groups/{id}": {
        "operationId": "update_group_api_groups__id__patch",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "POST /api/groups/{id}/user/{user_id}": {
        "operationId": "add_member_api_groups__id__user__user_id__post",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "DELETE /api/groups/{id}/user/{user_id}": {
        "operationId": "remove_member_api_groups__id__user__user_id__delete",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "DELETE /api/groups/{id}": {
        "operationId": "delete_group_api_groups__id__delete",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "POST /api/chatbots/{id}/group/{group_id}": {
        "operationId": "add_group_api_chatbots__id__group__group_id__post",
        "parameters": {"group_id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `group_id` value",
    },
    "DELETE /api/chatbots/{id}/group/{group_id}": {
        "operationId": "remove_group_api_chatbots__id__group__group_id__delete",
        "parameters": {"group_id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `group_id` value",
    },
}


def get_group_by_id(
    id: GroupId,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.GROUPS])],
) -> Group:
    group: Group | None = session.get(Group, id)
    if group is None:
        raise GroupNotFoundError
    if group.owner_id != user.id:
        raise NotAuthorizedError
    return group


def get_user_by_id(user_id: UserId, session: Annotated[Session, Depends(db_engine.get_session)]) -> User:
    user: User | None = session.get(User, user_id)
    if user is None:
        raise UserNotFoundError
    return user


@gr.post(
    "",
    response_model=GroupPublicWithChatbots,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"links": links},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
    },
)
def create_group(
    *,
    group_data: GroupCreate,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.GROUPS])],
) -> Group:
    group = Group(
        name=group_data.name,
        description=group_data.description,
        icon=group_data.icon,
        member=[user],
        owner=user,
        owner_id=user.id,
    )
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


@gr.post(
    "/{id}/user/{user_id}",
    response_model=GroupPublic,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "POST /api/groups/{id}/user/{user_id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
        status.HTTP_409_CONFLICT: {"model": ErrorMessage},
    },
)
def add_member(
    *,
    group: Annotated[Group, Depends(get_group_by_id)],
    user: Annotated[User, Depends(get_user_by_id)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> Group:
    if group.id == ALL_USERS_GROUP_ID:
        raise GroupModificationError
    group.member.append(user)
    session.add(group)
    try:
        session.commit()
    except IntegrityError as e:
        # TODO: refactor
        raise UserInGroupError from e
    session.refresh(group)
    return group


@gr.delete(
    "/{id}/user/{user_id}",
    response_model=GroupPublic,
    responses={
        status.HTTP_200_OK: {
            "links": {k: v for k, v in links.items() if k != "DELETE /api/groups/{id}/user/{user_id}"}
        },
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def remove_member(
    *,
    group: Annotated[Group, Depends(get_group_by_id)],
    user: Annotated[User, Depends(get_user_by_id)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> Group:
    if group.id == ALL_USERS_GROUP_ID:
        raise GroupModificationError
    group.member.remove(user)
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


@gr.patch(
    "/{id}",
    response_model=GroupPublicWithChatbots,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "PATCH /api/groups/{id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def update_group(
    *,
    group: Annotated[Group, Depends(get_group_by_id)],
    group_update: GroupUpdate,
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> Group:
    if group.id == ALL_USERS_GROUP_ID:
        raise GroupModificationError
    group_data = group_update.model_dump(exclude_unset=True)
    for k, v in group_data.items():
        if v is not None and getattr(group, k) != v:
            setattr(group, k, v)
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


@gr.delete(
    "/{id}",
    response_model=StatusMessage,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "DELETE /api/groups/{id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def delete_group(
    *,
    group: Annotated[Group, Depends(get_group_by_id)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> StatusMessage:
    if group.id == ALL_USERS_GROUP_ID:
        raise GroupRemoveError
    session.delete(group)
    session.commit()
    return StatusMessage(ok=True, message=f"Deleted group {group.name}")


@gr.get(
    "/{id}",
    response_model=GroupPublicWithChatbots,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "GET /api/groups/{id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def get_group(*, group: Annotated[Group, Depends(get_group_by_id)]) -> Group:
    return group


@gr.get(
    "",
    response_model=list[GroupPublicWithChatbots],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
    },
)
@gr.get("/debug", include_in_schema=False)
def get_groups(
    *,
    list_filter: Annotated[ListFilter, Query()],
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.GROUPS])],
) -> list[Group]:
    """Get a list of all groups.

    Offset and limit can be controlled for pagination.
    """
    groups = session.exec(
        select(Group)
        .where(Group.owner_id == user.id)
        .order_by(col(Group.modified).desc())
        .offset(list_filter.offset)
        .limit(list_filter.limit),
    ).all()
    return list(groups)
