from enum import StrEnum


# comments show original error messages for reference
# TODO: delete original error message after adding support for i18n.ErrorCode Messages in the frontend
class ErrorCode(StrEnum):
    VALIDATION_ERROR = "backend.error.validation-error"
    INTERNAL_SERVER_ERRROR = "backend.error.internal-server-error"
    CANT_CHANGE_SUPERADMIN_PERMISSION = (
        "backend.error.cant-change-superadmin-permission"  # "Superadmin needs to be superadmin"
    )
    CANT_DELETE_SUPERADMIN = "backend.error.cant-delete-superadmin"  # "Cannot delete superuser"
    CHATBOT_ALREADY_OWNED = "backend.error.chatbot-already-owned"  # "Chatbot already owned by user"
    CHATBOT_MISSING = "backend.error.chatbot-missing"  # "Chatbot missing"
    CHATBOT_NOT_FOUND = "backend.error.chatbot-not-found"  # "Chatbot not found"
    CHATBOT_SHARED_GROUP = "backend.error.chatbot-shared-group"  # "Chatbot already shared with group"
    CHATBOT_SHARED_USER = "backend.error.chatbot-shared-user"  # "Chatbot already shared with this user"
    CONVERSATION_NOT_FOUND = "backend.error.conversation-not-found"  # "Conversation not found"
    LLM_NOT_FOUND = "backend.error.llm-not-found"  # "LLM not found"
    CONVERSATION_TITLE_NOT_FOUND = (
        "backend.error.conversation-title-not-found"  # "Could not get title for conversation"
    )
    FILE_EXISTS = "backend.error.file-exists"  # "File already exists"
    FILE_EXISTS_FOR_USER = "backend.error.file-exists-for-user"  # "File already exists for this user"
    FILE_EXPIRED = "backend.error.file-expired"  # "File expired"
    FILE_NOT_FOUND = "backend.error.file-not-found"  # "File not found"
    FILE_S_LINKED_TO_CHATBOT = "backend.error.file-s_linked-to-chatbot"  # f"File(s) already linked to chatbot: {[str(id) for id in duplicates]}"
    FILE_S_NOT_FOUND = "backend.error.file-s-not-found"  # f"File(s) not found: {[str(f) for f in chatbot.files if f not in {df.id for df in db_files}]}"
    FILE_S_INVALID_STATUS = "backend.error.file-s-invalid-status"  # File(s) has(ve) 'pending' or 'failed' status
    FILE_TOO_LARGE = "backend.error.file-too-large"  # f"File too large, max {MAX_FILE_SIZE_MB} MB allowed"
    DIRECTORY_NOT_FOUND = "backend.error.directory-not-found"
    DIRECTORY_EXISTS = "backend.error.directory-exists"
    DIRECTORY_CYCLE = "backend.error.directory-cycle"
    CANT_DELETE_ROOT_DIRECTORY = "backend.error.cant-delete-root-directory"
    CANT_MOVE_ROOT_DIRECTORY = "backend.error.cant-move-root-directory"
    GROUP_NOT_FOUND = "backend.error.group-not-found"  # "Group not found"
    GROUP_CAN_NOT_BE_MODIFIED = "backend.error.group-can-not-be-modified-manually"  # Group can not be modified manually
    GROUP_CAN_NOT_BE_DELETED = "backend.error.group-can-not-be-deleted"  # Group can not be deleted
    INCORRECT_PASSWORD = "backend.error.incorrect-password"  # noqa: S105 # "Incorrect password"
    INSUFFICIENT_PERMISSIONS = "backend.error.insufficient-permissions"  # "Not enough permissions"
    INVALID_CREDENTIALS = "backend.error.invalid-credentials"  # "Could not validate credentials"
    INVALID_USER_PROVIDED_CREDENTIALS = (
        "backend.error.invalid-user-provided-credentials"  # "Incorrect username or password"
    )
    MESSAGE_FROM_USER_EXPECTED = "backend.error.message-from-user-expected"  # "There must be a message from the user"
    MESSAGE_NOT_FOUND = "backend.error.message-not-found"  # "Message not found"
    NO_MESSAGES_PROVIDED = "backend.error.no-messages-provided"  # "No messages provided"
    NOT_AUTHORIZED = "backend.error.not-authorized"  # "Not authorized"
    RATE_ONLY_AI_MESSAGES = "backend.error.rate-only-ai-messages"  # "Only AI messages are allowed to be rated."
    UNABLE_TO_DELETE_FILE = "backend.error.unable-to-delete-file"  # str(e) in try/except when deleting store_object
    UNABLE_TO_STORE_FILE = "backend.error.unable-to-store-file"  # str(e) in try/except where store_object gets called
    UNSUPPORTED_MEDIA_TYPE = "backend.error.unsupported-media-type"  # f"Media type {file.content_type} not supported"
    USER_EXISTS = "backend.error.user-exists"  # "User already exists"
    USER_IN_GROUP = "backend.error.user-in-group"  # "User already in group"
    USER_NOT_AUTHORIZED = "backend.error.user-not-authorized"  # "User does not have access to requested scope(s)"
    USER_NOT_FOUND = "backend.error.user-not-found"  # "User not found"
    TOO_MANY_REQUESTS = "backend.error.too-many-requests"  # "Too many requests have been made"
    INDEX_NOT_FOUND = "backend.error.index-not-found"  # weaviate index not found
    INDEXER_NOT_INITIALIZED = "backend.error.indexer-was-not-initialized"  # indexer was not initialized
    NOT_VALID_PROVIDER_MODEL = (
        "backend.error.not-valid-provider-model"  # Not valid model was choosen for current LLM provider
    )
    NOT_THE_LAST_MESSAGE = (
        "backend.error.not-the-last-message-was-chosen-for-editing"  # Not the last message was chosen for editing
    )
