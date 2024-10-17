from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Form,
    Query,
    Security,
    UploadFile,
    status,
)
from fastapi import File as FileFastApi
from fastapi.responses import FileResponse, StreamingResponse
from minio.error import S3Error
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, or_, select
from weaviate.exceptions import WeaviateConnectionError

from app.api.exceptions import (
    DirectoryNotFoundError,
    FileExistsForUserError,
    FileExpiredError,
    FileTooLargeError,
    NotAuthorizedError,
    TsaiFileExistsError,
    TsaiFileNotFoundError,
    UnableToDeleteFileError,
    UnableToStoreFileError,
    UnsupportedMediaTypeError,
)
from app.api.models import (
    Directory,
    DirectoryId,
    ErrorMessage,
    File,
    FileId,
    FilePublic,
    FileUpdate,
    FileUser,
    IndexingStatus,
    ListFilter,
    Scope,
    StatusMessage,
    User,
    UserId,
)
from app.api.routers import FILES_PREFIX
from app.api.tools.auth import get_current_user
from app.api.tools.db import db_engine
from app.custom_logging import get_logger
from app.engine.file_remover import remove_file_from_vectordb
from app.engine.object_store import object_store
from app.settings import AdminSettings, get_admin_settings
from app.settings import settings as app_settings

MAX_FILE_SIZE_MB = 50


class SupportedMimeTypes(StrEnum):
    # From https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
    PDF = "application/pdf"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


ALLOWED_MEDIA_TYPES = set(SupportedMimeTypes)

logger = get_logger(__name__)

file_router = fr = APIRouter(prefix=FILES_PREFIX, tags=["files"])

links = {
    "GET /api/files/{id}": {
        "operationId": "get_file_api_files__id__get",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "GET /api/files/download/{id}": {
        "operationId": "download_file_api_files_download__id__get",
        "parameters": {"id": "$response.body#/id", "file_name": ""},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "GET /api/files/download/{id}/{file_name}": {
        "operationId": "download_file_with_name_api_files_download__id___file_name__get",
        "parameters": {"id": "$response.body#/id", "file_name": ""},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "PATCH /api/files/{id}": {
        "operationId": "patch_file_api_files__id__patch",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "PATCH /api/files/reupload/{id}": {
        "operationId": "reupload_api_files_reupload__id__patch",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "PATCH /api/files/{id}/reindex": {
        "operationId": "reindex_file_api_files__id__reindex_patch",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "DELETE /api/files/{id}": {
        "operationId": "delete_file_api_files__id__delete",
        "parameters": {"id": "$response.body#/id"},
        "description": "The `id` value returned in the response can be used as the `id` value",
    },
    "POST /api/chatbots": {
        "operationId": "create_chatbot_api_chatbots_post",
        "requestBody": {"files": ["$response.body#/id"]},
        "description": "The `id` value returned in the response can be used as a `file_id` value",
    },
    "GET /api/directories/{id}": {
        "operationId": "get_directory_api_directories__id__get",
        "parameters": {"id": "$response.body#/root_directory/id"},
        "description": "The `id` of the `root_directory` object returned in the response can be used as the `id` value",
    },
    "PATCH /api/directories/{id}": {
        "operationId": "move_directory_api_directories__id__patch",
        "parameters": {"id": "$response.body#/root_directory/id"},
        "description": "The `id` of the `root_directory` object returned in the response can be used as the `id` value",
    },
    "DELETE /api/directories/{id}": {
        "operationId": "delete_directory_api_directories__id__delete",
        "parameters": {"id": "$response.body#/root_directory/id"},
        "description": "The `id` of the `root_directory` object returned in the response can be used as the `id` value",
    },
}


def validate_file(file: UploadFile) -> UploadFile:
    if file.size and file.size > MAX_FILE_SIZE_MB * 1024**2:
        logger.info("file %s exceeded max size of %s", file.filename, MAX_FILE_SIZE_MB)
        raise FileTooLargeError(max_file_size_mb=MAX_FILE_SIZE_MB, actual_file_size_mb=file.size / 1024**2)
    if not file.content_type or file.content_type not in ALLOWED_MEDIA_TYPES:
        logger.info(
            "file %s rejected due to forbidden media type %s",
            file.filename,
            file.content_type,
        )
        raise UnsupportedMediaTypeError(file.content_type)
    return file


def _get_file_by_id(id: FileId, session: Session) -> FileUser:
    file: FileUser | None = session.get(FileUser, id)
    if not file:
        raise TsaiFileNotFoundError
    if file.expires and file.expires < datetime.now(tz=UTC):
        raise FileExpiredError
    return file


def get_file_by_id_owned(
    id: FileId,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.FILES])],
) -> FileUser:
    file = _get_file_by_id(id, session)
    if file.owner_id != user.id:
        raise NotAuthorizedError
    return file


def get_file_by_id_owned_or_shared(
    id: FileId,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.FILES])],
) -> FileUser:
    file = _get_file_by_id(id, session)
    if file.owner_id != user.id and not file.shared_via_chatbot_with(user):
        raise NotAuthorizedError
    return file


def get_user_files_by_file_ids(
    file_ids: list[FileId],
    session: Session,
    file_owner_id: UserId,
) -> list[FileUser]:
    if not file_ids:
        return []
    files: list[FileUser] = list(
        session.exec(
            select(FileUser)
            .join(FileUser.file)  # type: ignore[reportArgumentType]
            .where(FileUser.owner_id == file_owner_id, col(File.id).in_(file_ids))
            .order_by(col(FileUser.modified).desc())
        ).all()
    )
    if not files:
        raise TsaiFileNotFoundError
    return files


def store_file(file: UploadFile, file_content: bytes, file_hash: str, namespace: str) -> File:
    assert file.content_type
    file_db = File(
        file_size=file.size or 0,
        mime_type=file.content_type,
        hash=file_hash,
        path="",
        pdf_path=None,
        namespace=namespace,
    )
    file_suffix = Path(file.filename or "").suffix
    file_db.path = f"data/uploads/{file_db.id}{file_suffix}"
    if file.content_type == SupportedMimeTypes.PDF:
        file_db.pdf_path = file_db.path
    try:
        object_store.store_object(
            app_settings.object_store_files_bucket_name,
            file_db.path,
            BytesIO(file_content),
        )
    except Exception as e:
        # TODO: test this code path
        logger.exception("Error while storing file", exc_info=e)
        raise UnableToStoreFileError from e
    return file_db


def delete_file_with_cleanup(file_user: FileUser, session: Session) -> None | Exception:
    if len(file_user.file.file_users) == 1:
        try:
            object_store.delete_object(app_settings.object_store_files_bucket_name, file_user.file.path)
            if file_user.file.pdf_path and file_user.file.pdf_path != file_user.file.path:
                object_store.delete_object(app_settings.object_store_files_bucket_name, file_user.file.pdf_path)
            assert file_user.file.id
            remove_file_from_vectordb(file_user.file.id)
            session.delete(file_user.file)
        except WeaviateConnectionError as e:
            # TODO: test this
            return e
        # TODO: what happens if session.delete throws Error, but file is deleted from vector?! Fix
    # If the file_user object needs to be deleted too, you need to add session.delete(file_user),
    # after this function was called and did return None (like in delete endpoint)
    return None


@fr.post(
    "/upload",
    response_model=FilePublic,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"links": links},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_409_CONFLICT: {"model": ErrorMessage},
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {"model": ErrorMessage},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"model": ErrorMessage},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorMessage},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorMessage},
    },
)
def upload(
    *,
    file: Annotated[UploadFile, Depends(validate_file)] = FileFastApi(),
    directory_id: Annotated[DirectoryId | None, Form()] = None,
    expires: Annotated[datetime | None, Form()] = None,
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.FILES])],
    admin_settings: Annotated[AdminSettings, Depends(get_admin_settings)],
) -> FileUser:
    """Upload a new file."""
    if directory_id is None:
        user = session.merge(user, load=False)
        directory = user.root_directory
    else:
        directory: Directory | None = session.get(Directory, directory_id)
        if directory is None:
            raise DirectoryNotFoundError(directory_id)
    if expires and expires.astimezone(tz=UTC) < datetime.now(tz=UTC):
        raise FileExpiredError
    try:
        file_content = file.file.read()
    finally:
        file.file.close()
    file_hash = sha256(file_content).hexdigest()
    logger.info("computed file hash for %s: %s", file.filename, file_hash)

    file_db: File | None = session.exec(select(File).where(File.hash == file_hash)).one_or_none()
    if file_db is not None:
        for file_user in file_db.file_users:
            if user == file_user.owner:
                raise FileExistsForUserError
    else:
        file_db = store_file(file, file_content, file_hash, admin_settings.namespace)

    file_user = FileUser(
        file_name=file.filename or "",
        directory=directory,
        directory_id=directory.id,
        expires=expires,
        owner=user,
        owner_id=user.id,
        chatbots=[],
        file=file_db,
    )

    file_db.file_users.append(file_user)
    try:
        session.add(file_db)
        session.add(file_user)
        session.commit()
        session.refresh(file_user)
    except IntegrityError as e:
        logger.info(e)
        raise TsaiFileExistsError from e
    return file_user


@fr.patch(
    "/reupload/{id}",
    response_model=FilePublic,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"links": links},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_409_CONFLICT: {"model": ErrorMessage},
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {"model": ErrorMessage},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"model": ErrorMessage},
        status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorMessage},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorMessage},
    },
)
def reupload(
    *,
    file_user: Annotated[FileUser, Depends(get_file_by_id_owned)],
    file: Annotated[UploadFile, Depends(validate_file)] = FileFastApi(),
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.FILES])],
    admin_settings: Annotated[AdminSettings, Depends(get_admin_settings)],
) -> FileUser:
    try:
        file_content = file.file.read()
    finally:
        file.file.close()

    file_hash = sha256(file_content).hexdigest()
    file_db: File | None = session.exec(select(File).where(File.hash == file_hash)).one_or_none()
    if file_db is not None:
        # Cases:
        # 1. current user got this file content in another file already
        # 2. other user got the same content uploaded already
        for enum_user in file_db.file_users:
            if user == enum_user.owner:
                # content did not change with reupload or user owns another file with this content
                raise FileExistsForUserError
    else:
        file_db = store_file(file, file_content, file_hash, admin_settings.namespace)

    err = delete_file_with_cleanup(file_user, session)
    if err is not None:
        raise UnableToDeleteFileError from err
    # File has more than 1 owner,
    # such that only the link between the user and file need to be unlinked
    linked_file = file_user.file
    linked_file.file_users.remove(file_user)
    session.add(linked_file)
    session.commit()

    file_db.file_users.append(file_user)
    session.add(file_db)
    session.commit()
    session.refresh(file_user)

    return file_user


def download_file_helper(file: FileUser, file_name: str | None, download: bool, original: bool) -> StreamingResponse:  # noqa: FBT001
    try:
        file_path = file.file.path if original or not file.file.pdf_path else file.file.pdf_path
        content = object_store.get_object(app_settings.object_store_files_bucket_name, file_path)
        return StreamingResponse(
            content=BytesIO(content),
            status_code=status.HTTP_200_OK,
            headers={
                "Content-Disposition": (
                    ("attachment" + f"; filename*={file_name}" if file_name else "") if download else "inline"
                )
            },
            media_type=file.file.mime_type,
        )
    except S3Error as e:
        # TODO: add test
        if e.code == "NoSuchKey":
            raise TsaiFileNotFoundError from None
        raise


@fr.get(
    "/download/{id}",
    response_class=FileResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def download_file(
    *,
    file: Annotated[FileUser, Depends(get_file_by_id_owned_or_shared)],
    download: Annotated[bool, Query()] = False,
    original: Annotated[bool, Query()] = False,
) -> StreamingResponse:
    """Download or preview a file by ID."""
    return download_file_helper(file, None, download, original)


@fr.get(
    "/download/{id}/{file_name}",
    response_class=FileResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def download_file_with_name(
    *,
    file: Annotated[FileUser, Depends(get_file_by_id_owned_or_shared)],
    file_name: str,
    download: Annotated[bool, Query()] = False,
    original: Annotated[bool, Query()] = False,
) -> StreamingResponse:
    """Download or preview a file by ID.

    The trailing file name path is returned as Content-Disposition.
    """
    return download_file_helper(file, file_name, download, original)


@fr.get(
    "",
    response_model=list[FilePublic],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
    },
)
@fr.get("/debug", include_in_schema=False)
def get_files(
    *,
    list_filter: Annotated[ListFilter, Query()],
    session: Annotated[Session, Depends(db_engine.get_session)],
    user: Annotated[User, Security(get_current_user, scopes=[Scope.FILES])],
) -> list[FileUser]:
    """Get a list of all files.

    Offset and limit can be controlled for pagination.
    """
    files = session.exec(
        select(FileUser)
        .where(
            FileUser.owner_id == user.id,
            or_(col(FileUser.expires).is_(None), col(FileUser.expires) >= datetime.now(tz=UTC)),
        )
        .order_by(col(FileUser.modified).desc())
        .offset(list_filter.offset)
        .limit(list_filter.limit),
    ).all()
    return list(files)


@fr.get(
    "/{id}",
    response_model=FilePublic,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "GET /api/files/{id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def get_file(
    *,
    file: Annotated[FileUser, Depends(get_file_by_id_owned_or_shared)],
) -> FileUser:
    """Get information about a file by ID."""
    return file


@fr.patch(
    "/{id}/reindex",
    response_model=FilePublic,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "GET /api/files/{id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def reindex_file(
    file_user: Annotated[FileUser, Depends(get_file_by_id_owned)],
    session: Annotated[Session, Depends(db_engine.get_session)],
    admin_settings: AdminSettings = Depends(get_admin_settings),
) -> FileUser:
    """Reindex a file by ID."""
    file = file_user.file
    file.namespace = admin_settings.namespace
    file.indexing_status = IndexingStatus.PENDING
    session.add(file)
    session.commit()
    session.refresh(file_user)
    return file_user


@fr.patch(
    "/{id}",
    response_model=FilePublic,
    responses={
        status.HTTP_200_OK: {"links": {k: v for k, v in links.items() if k != "PATCH /api/files/{id}"}},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def patch_file(
    *,
    file_user: Annotated[FileUser, Depends(get_file_by_id_owned)],
    file: FileUpdate,
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> FileUser:
    """Patch information about a file by ID."""
    modified = False
    if file.file_name is not None:
        file_user.file_name = file.file_name
        modified = True
    if file.directory_id is not None:
        directory: Directory | None = session.get(Directory, file.directory_id)
        if directory is None:
            raise DirectoryNotFoundError(file.directory_id)
        file_user.directory = directory
        file_user.directory_id = directory.id
        modified = True
    # need to use `model_fields_set` here to distinguish not wanting to change the file expiration and explicitly
    # setting it to (no longer) expire
    if "expires" in file.model_fields_set:
        file_user.expires = file.expires
        modified = True

    if modified:
        session.add(file_user)
        try:
            session.commit()
        except IntegrityError as e:
            raise TsaiFileExistsError from e
        session.refresh(file_user)
    return file_user


@fr.delete(
    "/{id}",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
        status.HTTP_404_NOT_FOUND: {"model": ErrorMessage},
    },
)
def delete_file(
    *,
    file_user: Annotated[FileUser, Depends(get_file_by_id_owned)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> StatusMessage:
    """Delete a file by ID."""
    err = delete_file_with_cleanup(file_user, session)
    if err is not None:
        return StatusMessage(ok=False, message=str(err))
    session.delete(file_user)
    session.commit()
    return StatusMessage(ok=True, message=f"File {file_user.file_name} deleted successfully.")
