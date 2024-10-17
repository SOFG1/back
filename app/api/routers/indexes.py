import json
import re
from typing import Annotated, Protocol, runtime_checkable

from fastapi import APIRouter, Depends, Request, Security, status
from pydantic import BaseModel, Field
from sqlmodel import Session, col, func, select, update
from weaviate import WeaviateClient
from weaviate.exceptions import UnexpectedStatusCodeError

from app.api.exceptions import IndexNotFoundError
from app.api.models import (
    CurrentIndexModelResponse,
    ErrorMessage,
    File,
    IndexingStatus,
    OldIndexesModelResponse,
    Scope,
    StatusMessage,
    User,
)
from app.api.tools.auth import get_current_user
from app.api.tools.db import db_engine
from app.settings import AdminSettings, get_admin_settings, logger

router = APIRouter(prefix="/api/indexes", tags=["indexes"])


@runtime_checkable
class HasRowcount(Protocol):
    rowcount: int


class ReindexResponse(BaseModel):
    files_to_reindex: Annotated[int, Field(ge=0)]
    dry_run: bool


def check_if_index_exists(client: WeaviateClient, index_name: str) -> None:
    try:
        str(client.collections.get(index_name))
    except UnexpectedStatusCodeError as e:
        raise IndexNotFoundError from e


def get_old_indexes(weaviate_client: WeaviateClient, current_index: str) -> OldIndexesModelResponse:
    return OldIndexesModelResponse(
        old_indexes=[
            w_index_data.name
            for w_index, w_index_data in weaviate_client.collections.list_all().items()
            if w_index.lower() != current_index.lower()
        ]
    )


def get_current_index_name(weaviate_str: str) -> str:
    pattern = r"config=(\{.*\})"

    match = re.search(pattern, weaviate_str, re.DOTALL)

    if not match:
        raise ValueError("Could not find JSON structure in the string.")  # noqa: TRY003, EM101

    json_str = match.group(1)

    try:
        config_dict = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(str(e)) from e

    return config_dict["name"]


@router.get(
    "/old",
    response_model=OldIndexesModelResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
    },
)
def list_old_indexes(
    _: Annotated[User, Security(get_current_user, scopes=[Scope.SETTINGS])],
    admin_settings: Annotated[AdminSettings, Depends(get_admin_settings)],
    request: Request,
) -> OldIndexesModelResponse:
    logger.info("Start fetching old indexes")
    result = get_old_indexes(request.app.state.weaviate_client, admin_settings.namespace)
    logger.info(f"Successfully fetched old indexes: {result}")
    return result


@router.delete(
    "/{index_name}",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def delete_index(
    index_name: str,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.SETTINGS])],
    request: Request,
) -> StatusMessage:
    logger.info(f"User {user.id} is attempting to delete index: {index_name}")
    client = request.app.state.weaviate_client
    check_if_index_exists(client=client, index_name=index_name)
    logger.info(f"Index '{index_name}' exists and will be deleted.")
    result = session.execute(update(File).where(col(File.namespace) == index_name).values(namespace=None))
    session.commit()
    assert isinstance(result, HasRowcount)
    updated_count = result.rowcount
    client.collections.delete(index_name)
    logger.info(f"Index '{index_name}' successfully deleted. {updated_count} file(s) now without namespace.")
    return StatusMessage(ok=True, message=f"Index '{index_name}' successfully deleted.")


@router.get(
    "/current",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
    },
)
def get_current_index(
    _: Annotated[User, Security(get_current_user, scopes=[Scope.SETTINGS])],
    admin_settings: Annotated[AdminSettings, Depends(get_admin_settings)],
    request: Request,
) -> CurrentIndexModelResponse:
    config = str(request.app.state.weaviate_client.collections.get(admin_settings.namespace))
    current_index = get_current_index_name(config)
    logger.info(f"Fetched current index: {current_index}")
    return CurrentIndexModelResponse(current_index=current_index)


@router.get(
    "/reindex/dry-run",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
    },
)
def get_files_to_reindex_dryrun(
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.SETTINGS])],
    admin_settings: AdminSettings = Depends(get_admin_settings),
) -> ReindexResponse:
    logger.info(
        f"User {user.id} is performing a dry-run check for reindexing files in namespace '{admin_settings.namespace}'"
    )
    count = session.exec(select(func.count(col(File.id))).where(File.namespace != admin_settings.namespace)).one()
    logger.info(f"Found {count} file(s) that need to be reindexed.")
    return ReindexResponse(files_to_reindex=count, dry_run=True)


@router.patch(
    "/reindex",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
    },
)
def reindex_files(
    *,
    session: Annotated[Session, Depends(db_engine.get_session)],
    admin_settings: AdminSettings = Depends(get_admin_settings),
    user: Annotated[User, Security(get_current_user, scopes=[Scope.SETTINGS])],
) -> ReindexResponse:
    """Number of files reindexed"""
    logger.info(f"User {user.id} is initiating reindexing for files not in namespace '{admin_settings.namespace}'")
    result = session.execute(
        update(File)
        .where(col(File.namespace) != admin_settings.namespace)
        .values(indexing_status=IndexingStatus.PENDING, namespace=admin_settings.namespace)
    )
    session.commit()
    assert isinstance(result, HasRowcount)
    updated_count = result.rowcount
    logger.info(f"Reindexed {updated_count} file(s).")
    return ReindexResponse(files_to_reindex=updated_count, dry_run=False)
