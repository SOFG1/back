import logging
import sys
import threading
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, RedirectResponse
from httpx import ConnectError
from langfuse import Langfuse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlmodel import Session, select

from app.api.exception_handlers import (
    internal_server_error_handler,
    rate_limit_exceeded_handler,
    standard_validation_exception_handler,
)
from app.api.models import (
    ADMIN_ID,
    ALL_USERS_GROUP_ID,
    ENTERPRISE_SEARCH_ID,
    LLM,
    Chatbot,
    Directory,
    Group,
    Health,
    User,
    Version,
)
from app.api.routers.chat import chat_router
from app.api.routers.chatbots import chatbot_router
from app.api.routers.conversation import conversation_router
from app.api.routers.directories import router as directory_router
from app.api.routers.files import file_router
from app.api.routers.groups import group_router
from app.api.routers.indexes import router as index_router
from app.api.routers.llms import llms_router
from app.api.routers.settings import settings_router
from app.api.routers.title import title_router
from app.api.routers.users import router as user_router
from app.api.tools.auth import get_password_hash
from app.api.tools.db import db_engine
from app.custom_logging import get_logger
from app.engine.client_getter import get_weaviate_client
from app.engine.converter import converter
from app.engine.index import cold_start_vector_db
from app.engine.indexer import indexer
from app.engine.object_store import object_store
from app.jobs.file_expiration import file_expiration_job
from app.langfuse_bedrock import setup_langfuse_prices
from app.metrics import add_metrics
from app.settings import get_admin_settings, limiter, settings

if TYPE_CHECKING:
    from weaviate import WeaviateClient

__version__ = settings.app_version
load_dotenv()
logging.basicConfig(level=logging.INFO)


def initialize_dependencies() -> None:
    cold_start_vector_db(settings)
    db_engine.connection_string = settings.db_connection_string
    db_engine.connection_pool_size = settings.db_connection_pool_size
    db_engine.create_schema()
    db_engine.create_engine()

    object_store.create_client(
        object_store_endpoint_url=settings.object_store_endpoint_url,
        object_store_access_key_id=settings.object_store_access_key_id,
        object_store_secret_access_key=settings.object_store_secret_access_key.get_secret_value(),
        object_store_secure=settings.object_store_secure,
    )
    if settings.object_store_auto_create_buckets:
        object_store.create_bucket_if_not_exists(settings.object_store_files_bucket_name)


def get_or_create_admin(session: Session) -> User:
    admin = session.get(User, ADMIN_ID)
    if admin is None:
        admin = User(
            id=ADMIN_ID,
            username="admin",
            name=settings.admin_name,
            email="admin@skillbyte.de",
            password_hash=get_password_hash("skillbyte"),
            scopes="*",
            avatar="https://www.skillbyte.de/wp-content/uploads/2024/06/cropped-favicon-192x192.png",
        )
        admin.root_directory = Directory(name="/", canonical="/", owner_id=admin.id, owner=admin)
        session.add(admin)
        session.commit()
        session.refresh(admin)
    return admin


def get_or_create_enterprise_search(session: Session, admin: User) -> Chatbot:
    enterprise_search = session.get(Chatbot, ENTERPRISE_SEARCH_ID)
    if enterprise_search is None:
        enterprise_search = Chatbot(
            name="Enterprise Search",
            owner=admin,
            owner_id=admin.id,
            description="Hallo! Ich helfe dir dabei, effizient Daten und Dokumente zu finden. Frag mich einfach!",
            system_prompt="Du bist der KI Assistent 'Enterprise Search', welcher Leuten hilft, Antworten auf unternehmensspezifische Fragen zu finden.",
            citations_mode=True,
            id=ENTERPRISE_SEARCH_ID,
            color="#404999",
            icon="enterprise-search",
        )
        session.add(enterprise_search)
        session.commit()
        session.refresh(enterprise_search)
    return enterprise_search


def initialize_llm_if_needed(session: Session) -> None:
    if session.exec(select(LLM)).first() is None:
        logger = get_logger("LLM")
        logger.info("no LLM configured - initializing with default values")
        admin_settings = get_admin_settings(session)
        llm = LLM(
            display_name=admin_settings.default_llm_display_name,
            provider=admin_settings.default_llm_provider,
            llm_model_name=admin_settings.default_llm_model_name,
            title_model_name=admin_settings.default_llm_title_model_name,
            temperature=admin_settings.default_llm_temperature,
            title_temperature=admin_settings.default_llm_title_temperature,
            max_tokens=admin_settings.default_llm_max_tokens,
            top_p=admin_settings.default_llm_top_p,
            context_length=admin_settings.default_llm_context_length,
        )
        session.add(llm)
        session.commit()


def initialize_all_users_group_if_needed(session: Session, admin: User, enterprise_search: Chatbot) -> None:
    if session.get(Group, ALL_USERS_GROUP_ID) is None:
        group = Group(
            id=ALL_USERS_GROUP_ID,
            name=settings.all_users_group_name,
            description="Default group for all users",
            icon="all-users-group",
            owner=admin,
            owner_id=admin.id,
            member=[admin],
            chatbots=[enterprise_search],
        )
        session.add(group)
        session.commit()
    session.execute(
        text("""
            INSERT INTO usergrouplink (user_id, group_id)
            SELECT u.id, :all_users_group_id
            FROM "user" u
            LEFT JOIN usergrouplink ugl
            ON u.id = ugl.user_id AND ugl.group_id = :all_users_group_id
            WHERE ugl.group_id IS NULL;
        """),
        {"all_users_group_id": ALL_USERS_GROUP_ID},
    )


def initialize_indexer_and_converter(app: FastAPI, session: Session) -> None:
    def start_threads(thread_count: int, target_function: Callable, name_prefix: str) -> None:
        if thread_count > 0:
            for i in range(thread_count):
                threading.Thread(target=target_function, name=f"{name_prefix}-{i}", daemon=True).start()
        else:
            logger.info(f"{name_prefix} disabled")  # noqa: G004

    admin_settings = get_admin_settings(session)
    indexer.initialize(admin_settings.namespace)
    app.state.indexer = indexer
    start_threads(settings.num_document_indexer_threads, indexer.poll_continuously, "indexer")
    start_threads(settings.num_document_converter_threads, converter.poll_continuously, "converter")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    logger = get_logger("startup")
    logger.info("settings: %s", settings)
    initialize_dependencies()
    app.state.limiter = limiter
    # initialize weaviate client needed for healthcheck
    app.state.weaviate_client = get_weaviate_client()
    # initialize langfuse client needed for healthcheck
    app.state.langfuse_client = Langfuse(enabled=False)

    with contextmanager(db_engine.get_session)() as session:
        # Create or retrieve the admin user
        admin = get_or_create_admin(session)

        # Create or retrieve the Enterprise Search chatbot
        enterprise_search = get_or_create_enterprise_search(session, admin)

        # Initialize LLM if needed
        initialize_llm_if_needed(session)

        # Create the Alle group and associate admin and chatbot
        initialize_all_users_group_if_needed(session, admin, enterprise_search)

        # Initialize document indexer and converter threads
        initialize_indexer_and_converter(app, session)

    # Set up Langfuse pricing configuration
    await setup_langfuse_prices()

    yield


if settings.job is not None:
    initialize_dependencies()
    match settings.job:
        case "file_expiration":
            file_expiration_job()
    sys.exit(0)

app = FastAPI(
    title="TextSenseAI Backend",
    lifespan=lifespan,
    version=__version__,
    default_response_class=ORJSONResponse,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_exception_handler(RequestValidationError, standard_validation_exception_handler)
app.add_exception_handler(status.HTTP_500_INTERNAL_SERVER_ERROR, internal_server_error_handler)


@app.get(
    "/",
    include_in_schema=False,
    response_class=RedirectResponse,
    status_code=status.HTTP_308_PERMANENT_REDIRECT,
)
def root() -> str:
    return "/api/docs"


@app.get("/api/version")
def version() -> Version:
    return Version(version=__version__)


@app.head("/health", include_in_schema=False)
@app.get(
    "/health",
    include_in_schema=False,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Health}},
)
def health(response: Response, request: Request) -> Health:
    health_status = Health()
    all_healthy = True
    weaviate_client: WeaviateClient = request.app.state.weaviate_client
    langfuse_client: Langfuse = request.app.state.langfuse_client

    try:
        with contextmanager(db_engine.get_session)() as session:
            session.exec(select(1))
        health_status.db_connection_healthy = True
    except Exception:
        all_healthy = False
        logger.exception("db connection status check failed")

    try:
        object_store.check_health()
        health_status.object_store_connection_healthy = True
    except Exception:
        all_healthy = False
        logger.exception("object store connection status check failed")

    if weaviate_client is None or not weaviate_client.is_live():
        all_healthy = False
        logger.exception("weaviate connection status check failed")
    health_status.weaviate_connection_healthy = True

    try:
        if langfuse_client is None or langfuse_client.client.health.health().status != "OK":
            all_healthy = False
            logger.exception("langfuse connection status check failed")
    except ConnectError:
        all_healthy = False
        logger.exception("langfuse connection status check failed")
    health_status.langfuse_connection_healthy = True

    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return health_status


if settings.environment == "dev":
    logger = get_logger("uvicorn")
    logger.warning("Running in development mode - allowing CORS for all origins")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


app.include_router(chat_router)
app.include_router(conversation_router)
app.include_router(title_router)
app.include_router(chatbot_router)
app.include_router(file_router)
app.include_router(user_router)
app.include_router(group_router)
app.include_router(settings_router)
app.include_router(llms_router)
app.include_router(directory_router)
app.include_router(index_router)
add_metrics(app)


if __name__ == "__main__":
    reload = settings.environment == "dev"
    uvicorn.run(
        app="main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=reload,
        reload_includes="app/*.py" if reload else None,
    )
