from pathlib import PosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, Security, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.api.exceptions import (
    CantDeleteRootDirectoryError,
    CantMoveRootDirectoryError,
    DirectoryCycleError,
    DirectoryExistsError,
    DirectoryNotFoundError,
    NotAuthorizedError,
)
from app.api.models import (
    Directory,
    DirectoryCreate,
    DirectoryId,
    DirectoryPublicWithChildren,
    DirectoryUpdate,
    ErrorMessage,
    Scope,
    StatusMessage,
    User,
)
from app.api.routers.files import delete_file_with_cleanup
from app.api.tools.auth import get_current_user
from app.api.tools.db import db_engine
from app.custom_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/directories", tags=["directories"])

links = {
    "GET /api/directories/{id}": {
        "operationId": "get_directory_api_directories__id__get",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "PATCH /api/directories/{id}": {
        "operationId": "move_directory_api_directories__id__patch",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "DELETE /api/directories/{id}": {
        "operationId": "delete_directory_api_directories__id__delete",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "PATCH /api/users/{id}": {
        "operationId": "patch_file_api_files__id__patch",
        "parameters": {"directory_id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
}


def get_directory_by_id(
    id: DirectoryId,
    user: Annotated[User, Security(get_current_user, scopes=[Scope.FILES])],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> Directory:
    directory: Directory | None = session.get(Directory, id)
    if directory is None:
        raise DirectoryNotFoundError(id)
    if directory.owner_id != user.id:
        raise NotAuthorizedError
    return directory


def detect_cycle(directory: Directory, new_parent: Directory) -> bool:
    current_parent = new_parent
    # Traverse until we reach the root directory or no parent
    while current_parent:
        if current_parent.id == directory.id:
            # A cycle is detected
            return True
        # Move upwards to the next parent
        current_parent = current_parent.parent
    # No cycle detected
    return False


@router.get(
    "/{id}",
    response_model=DirectoryPublicWithChildren,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "GET /api/directories/{id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def get_directory(
    directory: Annotated[Directory, Depends(get_directory_by_id)],
) -> Directory:
    return directory


@router.post(
    "",
    response_model=DirectoryPublicWithChildren,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"links": links},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
        status.HTTP_409_CONFLICT: {"model": ErrorMessage},
    },
)
def create_directory(
    *,
    directory_data: DirectoryCreate,
    user: Annotated[User, Security(get_current_user, scopes=[Scope.FILES])],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> Directory:
    parent = get_directory_by_id(directory_data.parent_id, user, session)
    directory = Directory(
        name=directory_data.name,
        owner=user,
        owner_id=user.id,
        canonical=str(PosixPath(parent.canonical) / directory_data.name),
        parent_id=parent.id,
        parent=parent,
    )
    session.add(directory)
    try:
        session.commit()
    except IntegrityError as e:
        raise DirectoryExistsError from e
    session.refresh(directory)
    return directory


@router.patch(
    "/{id}",
    response_model=DirectoryPublicWithChildren,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "PATCH /api/directories/{id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
        status.HTTP_409_CONFLICT: {"model": ErrorMessage},
    },
)
def move_directory(
    *,
    directory: Annotated[Directory, Depends(get_directory_by_id)],
    directory_update: DirectoryUpdate,
    user: Annotated[User, Security(get_current_user, scopes=[Scope.FILES])],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> Directory:
    if directory_update.parent_id is None and directory_update.name is None:
        return directory
    if directory.canonical == "/":
        raise CantMoveRootDirectoryError
    name = directory_update.name or directory.name
    directory.name = name
    if directory_update.parent_id is not None:
        new_parent = get_directory_by_id(directory_update.parent_id, user, session)
        if detect_cycle(directory, new_parent):
            raise DirectoryCycleError
        directory.canonical = str(PosixPath(new_parent.canonical) / name)
        directory.parent_id = new_parent.id
        directory.parent = new_parent
    session.add(directory)
    try:
        session.commit()
    except IntegrityError as e:
        raise DirectoryExistsError from e
    session.refresh(directory)
    return directory


@router.delete(
    "/{id}",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def delete_directory(
    *,
    directory: Directory = Depends(get_directory_by_id),
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> StatusMessage:
    if directory.canonical == "/":
        raise CantDeleteRootDirectoryError

    def delete_recursive(dir: Directory) -> None:
        for file in dir.files:
            err = delete_file_with_cleanup(file, session)
            if err is not None:
                raise err
            session.delete(file)
        for child in dir.children:
            delete_recursive(child)
        session.delete(dir)

    try:
        delete_recursive(directory)
    except Exception as e:
        return StatusMessage(ok=False, message=str(e))
    try:
        session.commit()
    except IntegrityError as e:
        return StatusMessage(ok=False, message=str(e))
    return StatusMessage(ok=True)
