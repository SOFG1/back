from uuid import UUID

from fastapi import HTTPException, status

from app.api.i18n import ErrorCode


class BackendError(HTTPException):
    error_code: ErrorCode
    status_code: int

    def __init__(
        self,
        *,
        extra: dict[str, str | int | float | list[str] | None] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        if extra is None:
            extra = {}
        super().__init__(
            status_code=self.status_code, detail={"error_code": self.error_code, "extra": extra}, headers=headers
        )


class CantChangeSuperadminPermissionError(BackendError):
    error_code = ErrorCode.CANT_CHANGE_SUPERADMIN_PERMISSION
    status_code = status.HTTP_403_FORBIDDEN


class CantDeleteSuperadminError(BackendError):
    error_code = ErrorCode.CANT_DELETE_SUPERADMIN
    status_code = status.HTTP_403_FORBIDDEN


class ChatbotAlreadyOwnedError(BackendError):
    error_code = ErrorCode.CHATBOT_ALREADY_OWNED
    status_code = status.HTTP_409_CONFLICT


class ChatbotMissingError(BackendError):
    error_code = ErrorCode.CHATBOT_MISSING
    status_code = status.HTTP_404_NOT_FOUND


class ChatbotNotFoundError(BackendError):
    error_code = ErrorCode.CHATBOT_NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, id: UUID | None = None) -> None:
        super().__init__(extra=None if id is None else {"id": str(id)})


class ChatbotSharedGroupError(BackendError):
    error_code = ErrorCode.CHATBOT_SHARED_GROUP
    status_code = status.HTTP_409_CONFLICT


class ChatbotSharedUserError(BackendError):
    error_code = ErrorCode.CHATBOT_SHARED_USER
    status_code = status.HTTP_409_CONFLICT


class ConversationNotFoundError(BackendError):
    error_code = ErrorCode.CONVERSATION_NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, id: UUID | None = None) -> None:
        super().__init__(extra=None if id is None else {"id": str(id)})


class LLMNotFoundError(BackendError):
    error_code = ErrorCode.LLM_NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, id: UUID | None = None) -> None:
        super().__init__(extra=None if id is None else {"id": str(id)})


class ConversationTitleNotFoundError(BackendError):
    error_code = ErrorCode.CONVERSATION_TITLE_NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND


class TsaiFileExistsError(BackendError):
    error_code = ErrorCode.FILE_EXISTS
    status_code = status.HTTP_409_CONFLICT


class FileExistsForUserError(BackendError):
    error_code = ErrorCode.FILE_EXISTS_FOR_USER
    status_code = status.HTTP_409_CONFLICT


class FileExpiredError(BackendError):
    error_code = ErrorCode.FILE_EXPIRED
    status_code = status.HTTP_410_GONE


class TsaiFileNotFoundError(BackendError):
    error_code = ErrorCode.FILE_NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, id: UUID | None = None) -> None:
        super().__init__(extra=None if id is None else {"id": str(id)})


class FileSLinkedToChatbotError(BackendError):
    error_code = ErrorCode.FILE_S_LINKED_TO_CHATBOT
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, duplicate_file_ids: list[str]) -> None:
        super().__init__(extra={"duplicate-file-ids": duplicate_file_ids})


class FileSNotFoundError(BackendError):
    error_code = ErrorCode.FILE_S_NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, file_ids: list[str]) -> None:
        super().__init__(extra={"file-ids-not-found": file_ids})


class FileSInvalidStatusError(BackendError):
    error_code = ErrorCode.FILE_S_INVALID_STATUS
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, file_ids: list[str]) -> None:
        super().__init__(extra={"file-s-invalid-status": file_ids})


class FileTooLargeError(BackendError):
    error_code = ErrorCode.FILE_TOO_LARGE
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE

    def __init__(self, max_file_size_mb: float, actual_file_size_mb: float) -> None:
        super().__init__(extra={"max-file-size-mb": max_file_size_mb, "actual-file-size-mb": actual_file_size_mb})


class GroupNotFoundError(BackendError):
    error_code = ErrorCode.GROUP_NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, id: UUID | None = None) -> None:
        super().__init__(extra=None if id is None else {"id": str(id)})


class IncorrectPasswordError(BackendError):
    error_code = ErrorCode.INCORRECT_PASSWORD
    status_code = status.HTTP_401_UNAUTHORIZED


class InsufficientPermissionsError(BackendError):
    error_code = ErrorCode.INSUFFICIENT_PERMISSIONS
    status_code = status.HTTP_403_FORBIDDEN


class InvalidCredentialsError(BackendError):
    error_code = ErrorCode.INVALID_CREDENTIALS
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self) -> None:
        super().__init__(headers={"WWW-Authenticate": "Bearer"})


class InvalidUserProvidedCredentialsError(BackendError):
    error_code = ErrorCode.INVALID_USER_PROVIDED_CREDENTIALS
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self) -> None:
        super().__init__(headers={"WWW-Authenticate": "Bearer"})


class MessageFromUserExpectedError(BackendError):
    error_code = ErrorCode.MESSAGE_FROM_USER_EXPECTED
    status_code = status.HTTP_400_BAD_REQUEST


class MessageNotFoundError(BackendError):
    error_code = ErrorCode.MESSAGE_NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, id: UUID | None = None) -> None:
        super().__init__(extra=None if id is None else {"id": str(id)})


class NoMessagesProvidedError(BackendError):
    error_code = ErrorCode.NO_MESSAGES_PROVIDED
    status_code = status.HTTP_400_BAD_REQUEST


class NotAuthorizedError(BackendError):
    error_code = ErrorCode.NOT_AUTHORIZED
    status_code = status.HTTP_403_FORBIDDEN


class RateOnlyAIMessagesError(BackendError):
    error_code = ErrorCode.RATE_ONLY_AI_MESSAGES
    status_code = status.HTTP_403_FORBIDDEN


class UnableToDeleteFileError(BackendError):
    error_code = ErrorCode.UNABLE_TO_DELETE_FILE
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class UnableToStoreFileError(BackendError):
    error_code = ErrorCode.UNABLE_TO_STORE_FILE
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class UnsupportedMediaTypeError(BackendError):
    error_code = ErrorCode.UNSUPPORTED_MEDIA_TYPE
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE

    def __init__(self, detected_media_type: str | None) -> None:
        str_detected_media_type = "application/octet-stream" if detected_media_type is None else detected_media_type
        super().__init__(extra={"detected-media-type": str_detected_media_type})


class UserExistsError(BackendError):
    error_code = ErrorCode.USER_EXISTS
    status_code = status.HTTP_409_CONFLICT


class UserInGroupError(BackendError):
    error_code = ErrorCode.USER_IN_GROUP
    status_code = status.HTTP_409_CONFLICT


class UserNotAuthorizedError(BackendError):
    error_code = ErrorCode.USER_NOT_AUTHORIZED
    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self) -> None:
        super().__init__(headers={"WWW-Authenticate": "Bearer"})


class UserNotFoundError(BackendError):
    error_code = ErrorCode.USER_NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, id: UUID | None = None) -> None:
        super().__init__(extra=None if id is None else {"id": str(id)})


class TooManyRequestsError(BackendError):
    error_code = ErrorCode.TOO_MANY_REQUESTS
    status_code = status.HTTP_429_TOO_MANY_REQUESTS


class DirectoryNotFoundError(BackendError):
    error_code = ErrorCode.DIRECTORY_NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, id: UUID | None = None) -> None:
        super().__init__(extra=None if id is None else {"id": str(id)})


class DirectoryExistsError(BackendError):
    error_code = ErrorCode.DIRECTORY_EXISTS
    status_code = status.HTTP_409_CONFLICT


class CantDeleteRootDirectoryError(BackendError):
    error_code = ErrorCode.CANT_DELETE_ROOT_DIRECTORY
    status_code = status.HTTP_403_FORBIDDEN


class CantMoveRootDirectoryError(BackendError):
    error_code = ErrorCode.CANT_MOVE_ROOT_DIRECTORY
    status_code = status.HTTP_403_FORBIDDEN


class DirectoryCycleError(BackendError):
    error_code = ErrorCode.DIRECTORY_CYCLE
    status_code = status.HTTP_409_CONFLICT


class GroupModificationError(BackendError):
    error_code = ErrorCode.GROUP_CAN_NOT_BE_MODIFIED
    status_code = status.HTTP_403_FORBIDDEN


class GroupRemoveError(BackendError):
    error_code = ErrorCode.GROUP_CAN_NOT_BE_DELETED
    status_code = status.HTTP_403_FORBIDDEN


class IndexNotFoundError(BackendError):
    error_code = ErrorCode.INDEX_NOT_FOUND
    status_code = status.HTTP_404_NOT_FOUND


class IndexerNotInitializedError(BackendError):
    error_code = ErrorCode.INDEXER_NOT_INITIALIZED
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class NotValidProviderModelError(BackendError):
    error_code = ErrorCode.NOT_VALID_PROVIDER_MODEL
    status_code = status.HTTP_400_BAD_REQUEST


class MessageUpdateError(BackendError):
    error_code = ErrorCode.NOT_THE_LAST_MESSAGE
    status_code = status.HTTP_400_BAD_REQUEST
