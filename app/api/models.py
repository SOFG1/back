from collections.abc import Generator
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Optional, TypeAlias
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, EmailStr, SecretStr, StringConstraints
from pydantic import Field as FieldPydantic
from pydantic_core import Url
from pydantic_extra_types.color import Color
from sqlalchemy import JSON, Column, DateTime, func
from sqlalchemy.orm import RelationshipProperty
from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint
from uuid6 import uuid7

from app.api import i18n
from app.api.routers import FILES_PREFIX
from app.api.tools.json_formatter import Output

ChatbotId: TypeAlias = UUID
ConversationId: TypeAlias = UUID
FileId: TypeAlias = UUID
MessageId: TypeAlias = UUID
UserId: TypeAlias = UUID
SpendLimitId: TypeAlias = UUID
GroupId: TypeAlias = UUID
LLMId: TypeAlias = UUID
DirectoryId: TypeAlias = UUID
# str that does not contain the NUL character (which would error in the DB)
NonNullString: TypeAlias = Annotated[str, StringConstraints(pattern="^[^\0]*$")]

ENTERPRISE_SEARCH_ID: ChatbotId = UUID("5dd4e868-96fc-4ef6-98b4-4589dd94b1bd")
ADMIN_ID: UserId = UUID("46e534d5-39b1-4c25-a6be-7f853d2d719e")
ALL_USERS_GROUP_ID: GroupId = UUID("34c7a5c5-2c82-4893-a206-d2438f77a239")
MAX_INT_32_BIT = 2**31 - 1


class LLMProvider(StrEnum):
    LOCAL = "local"
    OPENAI = "openai"
    BEDROCK = "bedrock"


class LLM(SQLModel, table=True):
    id: LLMId | None = Field(default_factory=uuid7, primary_key=True)
    display_name: Annotated[NonNullString, FieldPydantic(max_length=128)]
    provider: LLMProvider
    llm_model_name: NonNullString
    title_model_name: NonNullString
    temperature: Annotated[float, FieldPydantic(ge=0, le=1)]
    title_temperature: Annotated[float, FieldPydantic(ge=0, le=1)]
    max_tokens: Annotated[int, FieldPydantic(ge=0, le=MAX_INT_32_BIT)]
    top_p: Annotated[float, FieldPydantic(ge=0, le=1)]
    context_length: Annotated[int, FieldPydantic(ge=0, le=MAX_INT_32_BIT)]
    aws_region: NonNullString | None = FieldPydantic(
        default=None,
        min_length=9,
        max_length=15,
        pattern=r"^(af|ap|ca|eu|me|sa|us)-(central|north|(north(?:east|west))|south|south(?:east|west)|east|west)-\d{1,2}$",
    )

    model_config = ConfigDict(extra="forbid")  # type: ignore[reportAssignmentType]


class LLMPublic(BaseModel):
    id: LLMId
    display_name: NonNullString

    model_config = ConfigDict(extra="forbid")


class MessageRole(StrEnum):
    USER = "user"
    AI = "ai"


class ConversationData(BaseModel):
    message: NonNullString
    llm: LLMId

    model_config = ConfigDict(extra="forbid")


class TitleData(BaseModel):
    llm: LLMId

    model_config = ConfigDict(extra="forbid")


class StatusMessage(BaseModel):
    ok: bool
    message: NonNullString | None = None

    model_config = ConfigDict(extra="forbid")


class InfoMessage(BaseModel):
    message: str | None = None


class ErrorMessageDetail(BaseModel):
    error_code: i18n.ErrorCode
    extra: dict[str, str | int | float | list[str] | None] = {}

    model_config = ConfigDict(extra="forbid")


class ErrorMessage(BaseModel):
    detail: ErrorMessageDetail

    model_config = ConfigDict(extra="forbid")


class Health(BaseModel):
    db_connection_healthy: bool = False
    object_store_connection_healthy: bool = False
    weaviate_connection_healthy: bool = False
    langfuse_connection_healthy: bool = False

    model_config = ConfigDict(extra="forbid")


class Version(BaseModel):
    version: Annotated[str, FieldPydantic(pattern=r"v?\d+\.\d+\.\d+(-[a-zA-Z0-9-]+)?|dev", examples=["v1.0.0", "dev"])]

    model_config = ConfigDict(extra="forbid")


class Token(BaseModel):
    access_token: str
    token_type: str

    model_config = ConfigDict(extra="forbid")


class Scope(StrEnum):
    GROUPS = "groups"
    USERS = "users"
    FILES = "files"
    CHATBOTS = "chatbots"
    CONVERSATIONS = "conversations"
    SETTINGS = "settings"


class ListFilter(BaseModel):
    limit: int = Field(100, gt=0, le=100)
    offset: int = Field(0, ge=0, le=MAX_INT_32_BIT)

    model_config = ConfigDict(extra="forbid")


class CurrentIndexModelResponse(BaseModel):
    current_index: str


class OldIndexesModelResponse(BaseModel):
    old_indexes: list[str]


class ConversationMessageLink(SQLModel, table=True):
    conversation_id: ConversationId | None = Field(default=None, foreign_key="conversation.id", primary_key=True)
    message_id: MessageId | None = Field(default=None, foreign_key="dbmessage.id", primary_key=True, unique=True)


class ChatbotConversationLink(SQLModel, table=True):
    conversation_id: ConversationId | None = Field(
        default=None, foreign_key="conversation.id", primary_key=True, unique=True
    )
    chatbot_id: ChatbotId | None = Field(default=None, foreign_key="chatbot.id", primary_key=True)


class DBMessage(SQLModel, table=True):
    id: MessageId | None = Field(default_factory=uuid7, primary_key=True)
    role: MessageRole
    content: NonNullString
    conversation: "Conversation" = Relationship(
        back_populates="history", link_model=ConversationMessageLink, sa_relationship_kwargs={"lazy": "select"}
    )
    citations: list[Output] | None = Field(default=None, sa_type=JSON)
    trace_id: NonNullString | None = None
    observation_id: NonNullString | None = None
    feedback_value: float | None = Field(default=None, ge=0, le=1)
    created: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now()))
    modified: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )

    model_config = ConfigDict(extra="forbid")  # type: ignore[reportAssignmentType]


class UserConversationLink(SQLModel, table=True):
    user_id: UserId | None = Field(default=None, foreign_key="user.id", primary_key=True)
    conversation_id: ConversationId | None = Field(
        default=None, foreign_key="conversation.id", primary_key=True, unique=True
    )


class ConversationBase(SQLModel):
    title: NonNullString | None = Field(min_length=1, max_length=120)

    model_config = ConfigDict(extra="forbid")  # type: ignore[reportAssignmentType]


class Conversation(ConversationBase, table=True):
    id: ConversationId | None = Field(default_factory=uuid7, primary_key=True)

    history: list[DBMessage] = Relationship(
        back_populates="conversation",
        link_model=ConversationMessageLink,
        sa_relationship_kwargs={"lazy": "select", "order_by": "DBMessage.created"},
    )
    chatbot: "Chatbot" = Relationship(
        back_populates="conversations", link_model=ChatbotConversationLink, sa_relationship_kwargs={"lazy": "select"}
    )
    user: "User" = Relationship(
        back_populates="conversations", link_model=UserConversationLink, sa_relationship_kwargs={"lazy": "select"}
    )
    owner_id: UserId = Field(foreign_key="user.id")
    created: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now()))
    modified: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    citation_mode: bool | None = Field(default_factory=None)


class ConversationPublic(ConversationBase):
    id: ConversationId
    created: datetime
    modified: datetime


class ConversationPublicHistory(ConversationPublic):
    history: list[DBMessage]
    chatbot: "ChatbotPublic"
    created: datetime
    modified: datetime


class ConversationCreate(BaseModel):
    chatbot_id: ChatbotId = FieldPydantic(examples=[str(ENTERPRISE_SEARCH_ID)])

    model_config = ConfigDict(extra="forbid")


class TitleUpdate(BaseModel):
    title: NonNullString = Field(min_length=1, max_length=120)

    model_config = ConfigDict(extra="forbid")


class UserFileLink(SQLModel, table=True):
    user_id: UserId | None = Field(default=None, foreign_key="user.id", primary_key=True)
    file_user_id: FileId | None = Field(default=None, foreign_key="fileuser.id", primary_key=True, unique=True)


class UserChatbotLink(SQLModel, table=True):
    user_id: UserId | None = Field(default=None, foreign_key="user.id", primary_key=True)
    chatbot_id: ChatbotId | None = Field(default=None, foreign_key="chatbot.id", primary_key=True, unique=True)


class UserGroupLink(SQLModel, table=True):
    user_id: UserId | None = Field(default=None, foreign_key="user.id", primary_key=True)
    group_id: GroupId | None = Field(default=None, foreign_key="group.id", primary_key=True)


class UserOwnedGroupLink(SQLModel, table=True):
    user_id: UserId | None = Field(default=None, foreign_key="user.id", primary_key=True)
    group_id: GroupId | None = Field(default=None, foreign_key="group.id", primary_key=True, unique=True)


class UserSharedLink(SQLModel, table=True):
    user_id: UserId | None = Field(default=None, foreign_key="user.id", primary_key=True)
    chatbot_id: ChatbotId | None = Field(default=None, foreign_key="chatbot.id", primary_key=True)


class UserDirectoryLink(SQLModel, table=True):
    user_id: UserId | None = Field(default=None, foreign_key="user.id", primary_key=True)
    directory_id: DirectoryId | None = Field(default=None, foreign_key="directory.id", primary_key=True, unique=True)


class UserBase(SQLModel):
    username: NonNullString = Field(min_length=1, max_length=100, unique=True, index=True, regex=r"^[^#/?\s]*$")
    name: NonNullString = Field(min_length=1, max_length=100)

    model_config = ConfigDict(extra="forbid")  # type: ignore[reportAssignmentType]


class User(UserBase, table=True):
    id: UserId = Field(default_factory=uuid7, primary_key=True)
    email: EmailStr = Field(unique=True, index=True)
    password_hash: str = Field(regex=r"\$2(a|y|b)?\$\d+\$[A-Za-z0-9/\.]{53}")
    scopes: str = ""
    created: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now()))
    modified: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    conversations: list["Conversation"] = Relationship(
        back_populates="user", link_model=UserConversationLink, sa_relationship_kwargs={"lazy": "select"}
    )
    chatbots: list["Chatbot"] = Relationship(
        back_populates="owner", link_model=UserChatbotLink, sa_relationship_kwargs={"lazy": "select"}
    )
    shared_chatbots: list["Chatbot"] = Relationship(
        back_populates="individuals", link_model=UserSharedLink, sa_relationship_kwargs={"lazy": "select"}
    )
    groups: list["Group"] = Relationship(
        back_populates="member", link_model=UserGroupLink, sa_relationship_kwargs={"lazy": "select"}
    )
    files: list["FileUser"] = Relationship(
        back_populates="owner", link_model=UserFileLink, sa_relationship_kwargs={"lazy": "select"}
    )
    directories: list["Directory"] = Relationship(
        back_populates="owner",
        link_model=UserDirectoryLink,
        sa_relationship_kwargs={"lazy": "select", "overlaps": "root_directory, owner"},
    )
    root_directory: "Directory" = Relationship(
        sa_relationship=RelationshipProperty(
            "Directory",
            primaryjoin="and_(User.id == Directory.owner_id, Directory.canonical == '/')",
            uselist=False,
            cascade="all,delete",
            overlaps="directories, owner",
        )
    )
    owned_groups: list["Group"] = Relationship(
        back_populates="owner", link_model=UserOwnedGroupLink, sa_relationship_kwargs={"lazy": "select"}
    )
    avatar: NonNullString


class UserRegister(UserBase):
    email: EmailStr
    password: SecretStr = Field(min_length=6, max_length=100)
    avatar: AnyHttpUrl = Url("https://www.skillbyte.de/wp-content/uploads/2024/06/cropped-favicon-192x192.png")


class UserCreate(UserRegister):
    scopes: set[Scope] | set[Literal["*"]] = set()  # noqa: RUF012


class UserSetScopes(BaseModel):
    scopes: set[Scope] | set[Literal["*"]] = set()

    model_config = ConfigDict(extra="forbid")


class UserChangePassword(BaseModel):
    old_password: SecretStr = Field(min_length=6, max_length=100)
    new_password: SecretStr = Field(min_length=6, max_length=100)

    model_config = ConfigDict(extra="forbid")


class UserChangeName(BaseModel):
    name: Annotated[NonNullString, FieldPydantic(min_length=1, max_length=100)]

    model_config = ConfigDict(extra="forbid")


class UserChangeAvatar(BaseModel):
    avatar: AnyHttpUrl

    model_config = ConfigDict(extra="forbid")


class UserPublic(UserBase):
    id: UserId
    avatar: NonNullString


class UserPublicDetailed(UserPublic):
    created: datetime
    modified: datetime
    scopes: str = ""
    root_directory: "DirectoryPublic"


class GroupChatbotLink(SQLModel, table=True):
    group_id: GroupId | None = Field(default=None, foreign_key="group.id", primary_key=True)
    chatbot_id: ChatbotId | None = Field(default=None, foreign_key="chatbot.id", primary_key=True)


class GroupBase(SQLModel):
    name: NonNullString = Field(min_length=1, max_length=100)
    description: NonNullString = Field(max_length=1000)
    icon: NonNullString = Field(min_length=1, max_length=25)

    model_config = ConfigDict(extra="forbid")  # type: ignore[reportAssignmentType]


class Group(GroupBase, table=True):
    id: GroupId | None = Field(default_factory=uuid7, primary_key=True)
    member: list["User"] = Relationship(
        back_populates="groups", link_model=UserGroupLink, sa_relationship_kwargs={"lazy": "select"}
    )
    chatbots: list["Chatbot"] = Relationship(
        back_populates="groups", link_model=GroupChatbotLink, sa_relationship_kwargs={"lazy": "select"}
    )
    owner: User = Relationship(
        back_populates="owned_groups", link_model=UserOwnedGroupLink, sa_relationship_kwargs={"lazy": "select"}
    )
    owner_id: UserId = Field(foreign_key="user.id")
    created: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now()))
    modified: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )

    @staticmethod
    def is_all_users_group(group: "Group") -> bool:
        return group.id == ALL_USERS_GROUP_ID


class GroupCreate(GroupBase):
    icon: NonNullString = "default"


class GroupUpdate(BaseModel):
    name: NonNullString | None = Field(default=None, min_length=1, max_length=100)
    description: NonNullString | None = Field(default=None, max_length=1000)
    icon: NonNullString | None = Field(default=None, min_length=1, max_length=25)

    model_config = ConfigDict(extra="forbid")


class GroupPublic(GroupBase):
    id: GroupId
    member: list["UserPublic"]


class GroupPublicWithChatbots(GroupPublic):
    chatbots: list["ChatbotPublic"]


class ChatbotFileUserLink(SQLModel, table=True):
    chatbot_id: ChatbotId | None = Field(default=None, foreign_key="chatbot.id", primary_key=True)
    file_user_id: FileId | None = Field(default=None, foreign_key="fileuser.id", primary_key=True)


class ChatbotBase(SQLModel):
    name: NonNullString = Field(min_length=1, max_length=100)
    description: NonNullString = Field(max_length=1000)
    system_prompt: NonNullString = Field(min_length=1, max_length=2500)
    citations_mode: bool
    icon: NonNullString = Field(max_length=25)

    model_config = ConfigDict(extra="forbid")  # type: ignore[reportAssignmentType]


class Chatbot(ChatbotBase, table=True):
    id: ChatbotId | None = Field(default_factory=uuid7, primary_key=True)
    owner: "User" = Relationship(
        back_populates="chatbots", link_model=UserChatbotLink, sa_relationship_kwargs={"lazy": "select"}
    )
    owner_id: UserId = Field(foreign_key="user.id")
    files: list["FileUser"] = Relationship(
        back_populates="chatbots", link_model=ChatbotFileUserLink, sa_relationship_kwargs={"lazy": "select"}
    )
    groups: list["Group"] = Relationship(
        back_populates="chatbots", link_model=GroupChatbotLink, sa_relationship_kwargs={"lazy": "select"}
    )
    individuals: list["User"] = Relationship(
        back_populates="shared_chatbots", link_model=UserSharedLink, sa_relationship_kwargs={"lazy": "select"}
    )
    conversations: list[Conversation] = Relationship(
        back_populates="chatbot", link_model=ChatbotConversationLink, sa_relationship_kwargs={"lazy": "select"}
    )
    color: NonNullString = Field(max_length=50)
    created: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now()))
    modified: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    deleted: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class ChatbotCreate(ChatbotBase):
    files: set[FileId] = set()  # noqa: RUF012
    color: Color = FieldPydantic(examples=["red"])


class ChatbotUpdate(BaseModel):
    name: NonNullString | None = FieldPydantic(default=None, min_length=1, max_length=100)
    description: NonNullString | None = FieldPydantic(default=None, max_length=1000)
    color: Color | None = FieldPydantic(default=None, examples=["red"])
    system_prompt: NonNullString | None = FieldPydantic(default=None, min_length=1, max_length=2500)
    files: set[FileId] | None = None
    icon: NonNullString | None = FieldPydantic(default=None, max_length=25)
    citations_mode: bool | None = None

    model_config = ConfigDict(extra="forbid")


class ChatbotPublic(ChatbotBase):
    id: ChatbotId
    color: NonNullString
    owner_id: UserId
    groups: list["GroupPublic"]
    individuals: list["UserPublic"]
    created: datetime
    modified: datetime
    deleted: datetime | None


class ChatbotPublicWithFiles(ChatbotPublic):
    files: list["FilePublicNoChatbots"] = []  # noqa: RUF012


class FileFileUserLink(SQLModel, table=True):
    file_user_id: FileId | None = Field(default=None, foreign_key="fileuser.id", primary_key=True, unique=True)
    file_id: FileId | None = Field(default=None, foreign_key="file.id", primary_key=True)


class IndexingStatus(StrEnum):
    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"


class FileBase(SQLModel):
    __table_args__ = (UniqueConstraint("path", "pdf_path", name="path_with_pdf_path_unique"),)
    mime_type: NonNullString
    file_size: int
    path: NonNullString = Field(index=True, unique=True)
    pdf_path: NonNullString | None = Field(index=True)
    indexing_status: IndexingStatus = Field(default=IndexingStatus.PENDING, index=True)
    indexing_error: NonNullString | None = None

    model_config = ConfigDict(extra="forbid")  # type: ignore[reportAssignmentType]


class File(FileBase, table=True):
    id: FileId | None = Field(default_factory=uuid7, primary_key=True)
    hash: str | None = Field(default=None, index=True, unique=True, regex="[0-9a-f]{64}", max_length=64)
    file_users: list["FileUser"] = Relationship(
        back_populates="file", link_model=FileFileUserLink, sa_relationship_kwargs={"lazy": "select"}
    )
    created: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now()))
    modified: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    namespace: NonNullString | None = Field(index=True, nullable=False, min_length=1, max_length=256)


class FileUserBase(SQLModel):
    file_name: NonNullString = Field(min_length=1, max_length=256)

    model_config = ConfigDict(extra="forbid")  # type: ignore[reportAssignmentType]


class FileUser(FileUserBase, table=True):
    id: FileId | None = Field(default_factory=uuid7, primary_key=True)
    created: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now()))
    modified: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    expires: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    owner: User = Relationship(
        back_populates="files", link_model=UserFileLink, sa_relationship_kwargs={"lazy": "select"}
    )
    owner_id: UserId = Field(foreign_key="user.id")  # needed for the unique constraint
    chatbots: list[Chatbot] = Relationship(
        back_populates="files", link_model=ChatbotFileUserLink, sa_relationship_kwargs={"lazy": "select"}
    )
    file: "File" = Relationship(
        back_populates="file_users", link_model=FileFileUserLink, sa_relationship_kwargs={"lazy": "select"}
    )
    file_name: NonNullString
    directory_id: DirectoryId = Field(foreign_key="directory.id")  # needed for the unique constraint
    directory: "Directory" = Relationship(back_populates="files")
    __table_args__ = (
        UniqueConstraint("owner_id", "directory_id", "file_name", name="_user_directory_file_name_location_uc"),
    )

    @property
    def url(self) -> str:
        return f"{FILES_PREFIX}/download/{self.id}/{self.file_name}"

    def shared_via_chatbot_with(self, user: User) -> bool:
        return any(user in chatbot.individuals for chatbot in self.chatbots) or any(
            user in group.member for chatbot in self.chatbots for group in chatbot.groups
        )


class FilePublicNoChatbots(FileUserBase):
    id: FileId
    created: datetime
    modified: datetime
    expires: datetime | None
    owner: UserPublic
    directory: "DirectoryPublic"
    file: "File"


class FilePublic(FilePublicNoChatbots):
    chatbots: list[ChatbotPublic]


class FileUpdate(BaseModel):
    file_name: NonNullString | None = None
    directory_id: DirectoryId | None = None
    expires: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class SpendingLimitType(StrEnum):
    INPUT_TOKEN = "input-token"  # noqa: S105
    OUTPUT_TOKEN = "output-token"  # noqa: S105


class SpendingLimit(SQLModel, table=True):
    id: SpendLimitId | None = Field(default_factory=uuid7, primary_key=True)
    type: SpendingLimitType = Field(unique=True)
    value: int

    model_config = ConfigDict(extra="forbid")  # type: ignore[reportAssignmentType]


class FeedbackOptions(StrEnum):
    inaccurate = "Inaccurate"
    out_of_date = "Out of date"
    too_short = "Too short"
    too_long = "Too long"
    harmful_offensive = "Harmful or offensive"
    not_helpful = "Not helpful"


class Feedback(BaseModel):
    name: FeedbackOptions | Literal["user-explicit-feedback"] = FieldPydantic(..., description="Feedback type")
    value: float = FieldPydantic(..., le=1, ge=0)
    comment: NonNullString | None = Field(default=None, min_length=1, max_length=1000)

    model_config = ConfigDict(extra="forbid")


class AdminSetting(SQLModel, table=True):
    key: NonNullString = Field(primary_key=True)
    value: NonNullString
    created: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now()))
    modified: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )

    model_config = ConfigDict(extra="forbid")  # type: ignore[reportAssignmentType]


class DirectoryBase(SQLModel):
    name: Annotated[NonNullString, Field(min_length=1, max_length=128)]

    model_config = ConfigDict(extra="forbid")  # type: ignore[reportAssignmentType]


class Directory(DirectoryBase, table=True):
    id: DirectoryId = Field(default_factory=uuid7, primary_key=True)
    created: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now()))
    modified: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    )
    owner_id: UserId = Field(foreign_key="user.id", index=True)
    owner: User = Relationship(
        back_populates="directories", link_model=UserDirectoryLink, sa_relationship_kwargs={"lazy": "select"}
    )
    parent_id: DirectoryId | None = Field(default=None, foreign_key="directory.id", nullable=True)
    parent: Optional["Directory"] = Relationship(
        back_populates="children", sa_relationship_kwargs={"remote_side": "Directory.id"}
    )
    children: list["Directory"] = Relationship(back_populates="parent")
    files: list["FileUser"] = Relationship(back_populates="directory")
    canonical: NonNullString
    __table_args__ = (UniqueConstraint("owner_id", "canonical", name="_user_directory_uc"),)


class DirectoryCreate(DirectoryBase):
    parent_id: DirectoryId


class DirectoryUpdate(BaseModel):
    name: Annotated[NonNullString, FieldPydantic(min_length=1, max_length=128)] | None = None
    parent_id: DirectoryId | None = None

    model_config = ConfigDict(extra="forbid")


class DirectoryPublic(DirectoryBase):
    id: DirectoryId
    parent_id: DirectoryId | None
    canonical: NonNullString


class DirectoryPublicWithChildren(DirectoryPublic):
    files: list["FilePublic"]
    parent: Optional["DirectoryPublic"]
    children: list["DirectoryPublic"]


def get_subclasses(cls: type) -> Generator[type, None, None]:
    for subclass in cls.__subclasses__():
        yield from get_subclasses(subclass)
        yield subclass


for cls in get_subclasses(SQLModel):
    cls.model_rebuild()
