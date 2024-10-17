from collections.abc import Generator, Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Generic, NotRequired, Protocol, Self, TypedDict, TypeVar, Unpack
from unittest.mock import MagicMock, patch

import pytest
import weaviate
from fastapi.testclient import TestClient
from sqlalchemy_utils import database_exists, drop_database
from sqlmodel import Session
from uuid6 import uuid7

from app.api.models import (
    ADMIN_ID,
    ALL_USERS_GROUP_ID,
    ENTERPRISE_SEARCH_ID,
    LLM,
    Chatbot,
    ChatbotPublic,
    ChatbotPublicWithFiles,
    Conversation,
    ConversationPublic,
    DBMessage,
    Directory,
    DirectoryId,
    DirectoryPublic,
    File,
    FilePublic,
    FilePublicNoChatbots,
    FileUser,
    Group,
    GroupPublic,
    GroupPublicWithChatbots,
    IndexingStatus,
    LLMProvider,
    LLMPublic,
    MessageRole,
    User,
    UserId,
    UserPublic,
    UserPublicDetailed,
)
from app.api.tools.auth import get_password_hash
from app.api.tools.db import db_engine
from app.engine.indexer import Indexer
from app.engine.object_store import object_store
from app.settings import settings
from main import app
from tests.constants import DEFAULT_CREATED_MODIFIED_TIME, NEW_INDEX_TEST_NAMESPACE

T = TypeVar("T")


class AsyncIterator(Generic[T]):
    def __init__(self, seq: Iterable[T]) -> None:
        self.iter: Iterator[T] = iter(seq)

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> T:
        try:
            return next(self.iter)
        except StopIteration as e:
            raise StopAsyncIteration from e


def _append_test(key: str) -> None:
    value = getattr(settings, key)
    if not value.endswith("-test"):
        setattr(settings, key, f"{value}-test")


@pytest.fixture
def db_session() -> Generator[Session]:
    _append_test("db_database_name")
    if database_exists(settings.db_connection_string):
        # TODO: truncating all tables is probably faster
        drop_database(settings.db_connection_string)
    db_engine.connection_string = settings.db_connection_string
    db_engine.connection_pool_size = settings.db_connection_pool_size
    db_engine.create_schema()
    db_engine.create_engine()

    yield db_engine.get_session_raw()

    drop_database(settings.db_connection_string)


@pytest.fixture
def test_app(db_session: Session) -> TestClient:  # noqa:ARG001
    object_store.create_client(
        object_store_endpoint_url=settings.object_store_endpoint_url,
        object_store_access_key_id=settings.object_store_access_key_id,
        object_store_secret_access_key=settings.object_store_secret_access_key.get_secret_value(),
        object_store_secure=settings.object_store_secure,
    )
    _append_test("object_store_files_bucket_name")
    object_store.empty_bucket(settings.object_store_files_bucket_name)
    object_store.create_bucket_if_not_exists(settings.object_store_files_bucket_name)
    indexer = Indexer()
    indexer.initialize(NEW_INDEX_TEST_NAMESPACE)
    app.state.indexer = indexer
    app.state.weaviate_client = MagicMock()
    return TestClient(app)


@pytest.fixture
def test_user() -> User:
    with contextmanager(db_engine.get_session)() as session:
        admin: User | None = session.get(User, ADMIN_ID)
        if admin is None:
            admin = User(
                id=ADMIN_ID,
                username="admin",
                name="Test",
                email="admin@skillbyte.de",
                password_hash=get_password_hash("test"),
                scopes="*",
                avatar="https://www.example.com/favicon.png",
                conversations=[],
                chatbots=[],
                shared_chatbots=[],
                groups=[],
                files=[],
            )
            admin.root_directory = Directory(name="/", canonical="/", owner_id=admin.id, owner=admin)
            session.add(admin)
            session.commit()
            session.refresh(admin)
        return admin


@pytest.fixture
def test_group(test_user: User, db_session: Session) -> Group:
    test_user = db_session.merge(test_user)
    enterprise_search = db_session.get(Chatbot, ENTERPRISE_SEARCH_ID)
    if enterprise_search is None:
        enterprise_search = Chatbot(
            name="Enterprise Search",
            owner=test_user,
            owner_id=test_user.id,
            description="test description",
            system_prompt="test_prompt",
            citations_mode=True,
            id=ENTERPRISE_SEARCH_ID,
            color="#404999",
            icon="enterprise-search-test",
        )
        db_session.add(enterprise_search)

    all_users_group = db_session.get(Group, ALL_USERS_GROUP_ID)
    if not all_users_group:
        all_users_group = Group(
            id=ALL_USERS_GROUP_ID,
            name="Alle",
            description="Default group for all users",
            icon="all-users-group",
            owner=test_user,
            owner_id=test_user.id,
        )
        all_users_group.member.append(test_user)
        all_users_group.chatbots.append(enterprise_search)
        db_session.add(all_users_group)
    db_session.commit()
    db_session.refresh(all_users_group)
    return all_users_group


@pytest.fixture
def test_user_public(test_user: User) -> UserPublic:  # noqa: ARG001
    with contextmanager(db_engine.get_session)() as session:
        admin: User | None = session.get(User, ADMIN_ID)
        assert admin is not None
        return UserPublic(**admin.model_dump(include=set(UserPublic.model_fields)))


@pytest.fixture
def test_token(test_app: TestClient, test_user: User) -> str:  # noqa: ARG001
    # Get token
    response = test_app.post("/api/users/token", data={"username": "admin", "password": "test"})
    return response.json()["access_token"]


@pytest.fixture
def fake_user(db_session: Session) -> UserPublic:  # noqa: ARG001
    with contextmanager(db_engine.get_session)() as session:
        fake = User(
            id=uuid7(),
            username="fake",
            name="Fake",
            email="fake@skillbyte.de",
            password_hash=get_password_hash("fake"),
            scopes="*",
            avatar="https://www.example.com/favicon.png",
            conversations=[],
            chatbots=[],
            shared_chatbots=[],
            groups=[],
            files=[],
        )
        fake.root_directory = Directory(name="/", canonical="/", owner_id=fake.id, owner=fake)
        session.add(fake)
        session.commit()
        session.refresh(fake)
        return UserPublic(**fake.model_dump(include=set(UserPublic.model_fields)))


@pytest.fixture
def fake_user_detailed(test_app: TestClient, fake_user: UserPublic, test_token: str) -> UserPublicDetailed:
    resp = test_app.get(f"/api/users/{fake_user.id}", headers={"Authorization": f"Bearer {test_token}"})
    return UserPublicDetailed(**resp.json())


@pytest.fixture
def test_fake_token(test_app: TestClient, fake_user: UserPublic) -> str:
    # Get token
    response = test_app.post("/api/users/token", data={"username": fake_user.username, "password": "fake"})
    return response.json()["access_token"]


@pytest.fixture
def standard_user() -> UserPublic:
    with contextmanager(db_engine.get_session)() as session:
        user = User(
            id=uuid7(),
            username="user",
            name="User McUserface",
            email="user@skillbyte.de",
            password_hash=get_password_hash("password"),
            scopes="chatbots,conversations,files,groups",
            avatar="https://www.example.com/favicon.png",
            conversations=[],
            chatbots=[],
            shared_chatbots=[],
            groups=[],
            files=[],
        )
        user.root_directory = Directory(name="/", canonical="/", owner_id=user.id, owner=user)
        session.add(user)
        session.commit()
        session.refresh(user)
        return UserPublic(**user.model_dump(include=set(UserPublic.model_fields)))


@pytest.fixture
def test_user_token(test_app: TestClient, standard_user: UserPublic) -> str:
    # Get token
    response = test_app.post("/api/users/token", data={"username": standard_user.username, "password": "password"})
    return response.json()["access_token"]


class AddFile(Protocol):
    def __call__(
        self,
        path: Path,
        user: User | UserPublic,
        file_name: str = ...,
        expires: datetime | None = None,
        indexing_status: IndexingStatus = IndexingStatus.INDEXED,
    ) -> FilePublic: ...


@pytest.fixture
def add_file(test_app: TestClient) -> AddFile:  # noqa: ARG001
    def _add_file(
        path: Path,
        user: User | UserPublic,
        file_name: str = "test.pdf",
        expires: datetime | None = None,
        indexing_status: IndexingStatus = IndexingStatus.INDEXED,
    ) -> FilePublic:
        with contextmanager(db_engine.get_session)() as session:
            if isinstance(user, UserPublic):
                user_ = session.get(User, user.id)
                assert user_ is not None
                user = user_
            else:
                user = session.merge(user, load=False)
            file_id = uuid7()
            file_user_id = uuid7()
            with path.open("rb") as f:
                file_content = f.read()
                hash_ = sha256(file_content).hexdigest()
                object_store.store_object(
                    settings.object_store_files_bucket_name, f"data/uploads/{file_id}.pdf", BytesIO(file_content)
                )

            file_db = File(
                id=file_id,
                created=DEFAULT_CREATED_MODIFIED_TIME,
                modified=DEFAULT_CREATED_MODIFIED_TIME,
                mime_type="application/pdf",
                file_size=768,
                indexing_status=indexing_status,
                path=f"data/uploads/{file_id}.pdf",
                pdf_path=f"data/uploads/{file_id}.pdf",
                hash=hash_,
                file_users=[],
                namespace="test_namespace",
            )

            file_user = FileUser(
                id=file_user_id,
                file_name=file_name,
                owner=user,
                owner_id=user.id,
                file=file_db,
                chatbots=[],
                created=DEFAULT_CREATED_MODIFIED_TIME,
                modified=DEFAULT_CREATED_MODIFIED_TIME,
                expires=expires,
                directory=user.root_directory,
                directory_id=user.root_directory.id,
            )
            file_db.file_users.append(file_user)
            session.add(file_db)
            session.add(file_user)
            session.commit()
            session.refresh(file_user)
            assert file_user.id
            assert file_user.created
            assert file_user.modified
            return FilePublic(
                id=file_user.id,
                file_name=file_user.file_name,
                owner=UserPublic(**file_user.owner.model_dump(include=set(UserPublic.model_fields))),
                chatbots=[
                    ChatbotPublic(**c.model_dump(include=set(ChatbotPublic.model_fields))) for c in file_user.chatbots
                ],
                file=file_user.file,
                created=file_user.created,
                modified=file_user.modified,
                expires=file_user.expires,
                directory=DirectoryPublic(**file_user.directory.model_dump(include=set(DirectoryPublic.model_fields))),
            )

    return _add_file


@pytest.fixture
def test_chatbot(test_file: FilePublic, test_user: User) -> ChatbotPublicWithFiles:
    return _chatbot(
        file=test_file,
        user=test_user,
    )


@pytest.fixture
def test_chatbot_expired_file(test_file_expired: FilePublic, test_user: User) -> ChatbotPublicWithFiles:
    return _chatbot(
        file=test_file_expired,
        user=test_user,
    )


@pytest.fixture
def test_file(test_user: User, add_file: AddFile) -> FilePublic:
    return add_file(
        path=Path("data/testdocs/test.pdf"),
        user=test_user,
    )


@pytest.fixture
def test_file_status_pending(test_user: User, add_file: AddFile) -> FilePublic:
    return add_file(
        path=Path("data/testdocs/test_status_pending.pdf"),
        file_name="test_status_pending.pdf",
        user=test_user,
        indexing_status=IndexingStatus.PENDING,
    )


@pytest.fixture
def test_file_status_failed(test_user: User, add_file: AddFile) -> FilePublic:
    return add_file(
        path=Path("data/testdocs/test_status_failed.pdf"),
        file_name="test_status_failed.pdf",
        user=test_user,
        indexing_status=IndexingStatus.FAILED,
    )


@pytest.fixture
def test_file_expired(test_user: User, add_file: AddFile) -> FilePublic:
    return add_file(
        path=Path("data/testdocs/test.pdf"), user=test_user, expires=datetime(2020, 1, 1, 1, 0, 0, tzinfo=UTC)
    )


@pytest.fixture
def test_file_admin(test_user: User, add_file: AddFile) -> FilePublic:
    return add_file(
        path=Path("data/testdocs/test2.pdf"),
        user=test_user,
    )


@pytest.fixture
def test_chatbot_admin(test_file: FilePublic, test_user: User) -> ChatbotPublicWithFiles:
    return _chatbot(
        file=test_file,
        user=test_user,
    )


def _chatbot(file: FilePublic, user: User) -> ChatbotPublicWithFiles:
    with contextmanager(db_engine.get_session)() as session:
        test_file_db: FileUser | None = session.get(FileUser, file.id)
        assert test_file_db is not None
        chatbot = Chatbot(
            name="test_chatbot_fixture",
            description="description",
            system_prompt="system_prompt",
            citations_mode=True,
            files=[test_file_db],
            conversations=[],
            color="green",
            icon="default",
            owner=user,
            owner_id=user.id,
        )
        session.add(chatbot)
        session.commit()
        session.refresh(chatbot)
        return ChatbotPublicWithFiles(
            **chatbot.model_dump(include=set(ChatbotPublicWithFiles.model_fields)),
            groups=[GroupPublic(**g.model_dump(include=set(GroupPublic.model_fields))) for g in chatbot.groups],
            individuals=[UserPublic(**i.model_dump(include=set(UserPublic.model_fields))) for i in chatbot.individuals],
            files=[
                FilePublicNoChatbots(
                    **f.model_dump(include=set(FilePublicNoChatbots.model_fields)),
                    owner=UserPublic(**f.owner.model_dump(include=set(UserPublic.model_fields))),
                    file=f.file,
                    directory=DirectoryPublic(**f.directory.model_dump(include=set(DirectoryPublic.model_fields))),
                )
                for f in chatbot.files
            ],
        )


@pytest.fixture
def test_conversation(
    test_user: User,
    test_chatbot: ChatbotPublicWithFiles,
) -> ConversationPublic:
    with contextmanager(db_engine.get_session)() as session:
        chatbot: Chatbot | None = session.get(Chatbot, test_chatbot.id)
        assert chatbot is not None
        conversation = Conversation(title=None, history=[], chatbot=chatbot, user=test_user, owner_id=test_user.id)
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        return ConversationPublic(**conversation.model_dump(include=set(ConversationPublic.model_fields)))


@pytest.fixture
def test_conversation_expired_file(
    test_user: User,
    test_chatbot_expired_file: ChatbotPublicWithFiles,
) -> ConversationPublic:
    with contextmanager(db_engine.get_session)() as session:
        chatbot: Chatbot | None = session.get(Chatbot, test_chatbot_expired_file.id)
        assert chatbot is not None
        conversation = Conversation(title=None, history=[], chatbot=chatbot, user=test_user, owner_id=test_user.id)
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        return ConversationPublic(**conversation.model_dump(include=set(ConversationPublic.model_fields)))


class GroupFactoryKwargs(TypedDict):
    member: NotRequired[list[User | UserPublic]]
    name: NotRequired[str]
    description: NotRequired[str]
    icon: NotRequired[str]
    chatbots: NotRequired[list[Chatbot]]
    owner: NotRequired[User | UserPublic]


class GroupFactory(Protocol):
    def __call__(self, **kwargs: Unpack[GroupFactoryKwargs]) -> GroupPublicWithChatbots: ...


@pytest.fixture
def test_group_factory(
    test_user: User,
) -> GroupFactory:
    def _test_group_factory(**kwargs: Unpack[GroupFactoryKwargs]) -> GroupPublicWithChatbots:
        with contextmanager(db_engine.get_session)() as session:
            if "owner" in kwargs:
                owner = kwargs["owner"]
                if isinstance(owner, UserPublic):
                    owner = session.get(User, owner.id)
                    assert owner is not None
            else:
                owner = test_user
            if "member" in kwargs:
                members = [
                    m
                    for m in [session.get(User, m.id) if isinstance(m, UserPublic) else m for m in kwargs["member"]]
                    if m is not None
                ]
            else:
                members = [owner]
            group = Group(
                id=uuid7(),
                name=kwargs.get("name", "Finance"),
                description=kwargs.get("description", "Just a finance group"),
                icon=kwargs.get("icon", "default"),
                member=members,
                chatbots=kwargs.get("chatbots", []),
                owner=owner,
                owner_id=owner.id,
            )
            session.add(group)
            session.commit()
            session.refresh(group)
            return GroupPublicWithChatbots(
                **group.model_dump(include=set(GroupPublicWithChatbots.model_fields)),
                member=[UserPublic(**m.model_dump(include=set(UserPublic.model_fields))) for m in group.member],
                chatbots=[
                    ChatbotPublic(**c.model_dump(include=set(ChatbotPublic.model_fields))) for c in group.chatbots
                ],
            )

    return _test_group_factory


class DirectoryFactoryKwargs(TypedDict):
    name: NotRequired[str]
    parent_id: NotRequired[DirectoryId]
    owner_id: NotRequired[UserId]


class DirectoryFactory(Protocol):
    def __call__(self, **kwargs: Unpack[DirectoryFactoryKwargs]) -> DirectoryPublic: ...


@pytest.fixture
def test_directory_factory(fake_user_detailed: UserPublicDetailed) -> DirectoryFactory:
    def _test_directory_factory(**kwargs: Unpack[DirectoryFactoryKwargs]) -> DirectoryPublic:
        with contextmanager(db_engine.get_session)() as session:
            # Use test_user.root_directory.id as the fallback for parent_id if not provided
            parent_id = kwargs.get("parent_id", fake_user_detailed.root_directory.id)
            owner_id = kwargs.get("owner_id", fake_user_detailed.id)
            owner = session.get(User, owner_id)
            assert owner is not None
            directory = Directory(
                id=uuid7(),
                name=kwargs.get("name", "default_dir"),
                owner_id=owner_id,
                owner=owner,
                parent_id=parent_id,
                canonical=f"/{kwargs.get('name', 'default_dir')}",
            )
            session.add(directory)
            session.commit()
            session.refresh(directory)
            return DirectoryPublic(**directory.model_dump(include=set(DirectoryPublic.model_fields)))

    return _test_directory_factory


@pytest.fixture
def create_messages(db_session: Session, test_conversation: ConversationPublic) -> tuple[DBMessage, DBMessage]:
    conversation = db_session.get(Conversation, test_conversation.id)
    assert conversation is not None
    first_message_id = uuid7()
    second_message_id = uuid7()

    first_db_message = DBMessage(
        id=first_message_id, role=MessageRole.USER, content="test_message_1", conversation=conversation
    )
    second_db_message = DBMessage(
        id=second_message_id, role=MessageRole.USER, content="test_message_2", conversation=conversation
    )

    db_session.add_all([first_db_message, conversation])
    db_session.commit()
    db_session.add(second_db_message)
    db_session.commit()
    db_session.refresh(conversation)

    return first_db_message, second_db_message


@pytest.fixture
def test_llm() -> LLMPublic:
    with contextmanager(db_engine.get_session)() as session:
        llm = LLM(
            display_name="test model",
            provider=LLMProvider.BEDROCK,
            llm_model_name="test model",
            title_model_name="test title model",
            temperature=0.1,
            title_temperature=0.2,
            max_tokens=42,
            top_p=0.42,
            context_length=12,
        )
        session.add(llm)
        session.commit()
        assert llm.id
        return LLMPublic(id=llm.id, display_name=llm.display_name)


def get_pdf(cache_key: str) -> bytes:
    return f"""%PDF-1.0
%µ¶

1 0 obj
<</Type/Catalog/Pages 2 0 R>>
endobj

2 0 obj
<</Kids[3 0 R]/Count 1/Type/Pages/MediaBox[0 0 595 792]>>
endobj

3 0 obj
<</Type/Page/Parent 2 0 R/Contents 4 0 R/Resources<<>>>>
endobj

4 0 obj
<</Length 58>>
stream
q
BT
/ 96 Tf
1 0 0 1 36 684 Tm
(Hello World {cache_key}!) Tj
ET
Q

endstream
endobj

xref
0 5
0000000000 65536 f
0000000016 00000 n
0000000062 00000 n
0000000136 00000 n
0000000209 00000 n

trailer
<</Size 5/Root 1 0 R>>
startxref
316
%%EOF""".encode()


# Set up mocks
patch(
    "app.engine.client_getter.get_weaviate_client",
    new=MagicMock(return_value=MagicMock(weaviate.WeaviateClient, collections=MagicMock(), batch=MagicMock())),
).start()

patch(
    "app.engine.indexer.get_weaviate_client",
    new=MagicMock(return_value=MagicMock(weaviate.WeaviateClient, collections=MagicMock(), batch=MagicMock())),
).start()
patch(
    "app.engine.index.get_weaviate_client",
    new=MagicMock(return_value=MagicMock(weaviate.WeaviateClient, collections=MagicMock(), batch=MagicMock())),
).start()
patch(
    "app.engine.file_remover.get_weaviate_client",
    new=MagicMock(return_value=MagicMock(weaviate.WeaviateClient, collections=MagicMock(), batch=MagicMock())),
).start()
patch(
    "app.api.routers.chat.Chains",
    new=MagicMock(
        return_value=MagicMock(
            retriever_chain=MagicMock(invoke=MagicMock(return_value={"context": []})),
            get_conversational_chain=MagicMock(
                side_effect=lambda _, db_conversation: MagicMock(
                    astream=MagicMock(
                        return_value=AsyncIterator(
                            [
                                {"sources": []},
                                {"output": "test"},
                                *[{"output": " " + x.file_name} for x in db_conversation.chatbot.files],
                            ],
                        ),
                    ),
                ),
            ),
        ),
    ),
).start()
patch("app.api.routers.title.get_conversation_title", new=MagicMock(return_value="test title")).start()
patch("app.api.routers.conversation.get_conversation_title", new=MagicMock(return_value="test title")).start()
patch("app.engine.indexer.index").start()
