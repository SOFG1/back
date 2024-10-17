import os
import re
from collections import defaultdict
from collections.abc import Iterable
from functools import cached_property
from pathlib import Path
from typing import Annotated, Literal, Never, TypeAlias

from dotenv import load_dotenv
from fastapi import Depends
from langchain_aws import BedrockEmbeddings, ChatBedrockConverse
from langchain_community.llms.ollama import Ollama
from langchain_core.embeddings import Embeddings
from langchain_core.runnables import RunnableSerializable
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import Field, SecretStr, field_validator
from pydantic import Field as FieldPydantic
from pydantic_core.core_schema import FieldValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlmodel import Session, select

from app.api.exceptions import NotValidProviderModelError
from app.api.models import LLM, AdminSetting, LLMProvider, SpendingLimitType
from app.api.tools.db import db_engine
from app.custom_logging import get_logger

OpenAIModel: TypeAlias = Literal[
    "gpt-3.5-turbo",
    "gpt-4o",
    "gpt-4o-mini",
]
OpenAIEmbeddingModel: TypeAlias = Literal["text-embedding-3-large", "text-embedding-3-small", "text-embedding-ada-002"]

OllamaModel: TypeAlias = Literal[
    "llama3.1:70b",
    "llama3.1:8b",
    "llama3:70b",
    "llama3:8b",
    "mistral-large:123b",
    "gemma2:9b",
    "gemma2:27b",
    "qwen2:7b",
    "qwen2:72b",
]

BedrockModel: TypeAlias = Literal[
    "meta.llama3-1-8b-instruct-v1:0",
    "meta.llama3-1-70b-instruct-v1:0",
    "meta.llama3-1-405b-instruct-v1:0",
    "meta.llama3-8b-instruct-v1:0",
    "meta.llama3-70b-instruct-v1:0",
    "anthropic.claude-3-haiku-20240307-v1:0",
    "anthropic.claude-3-sonnet-20240229-v1:0",
    "anthropic.claude-3-opus-20240229-v1:0",
    "anthropic.claude-3-5-sonnet-20240620-v1:0",
]

LocalEmbeddingModel: TypeAlias = Literal["facebook/contriever", "intfloat/multilingual-e5-large"]

BedrockEmbeddingModel: TypeAlias = Literal["amazon.titan-embed-text-v2:0", "cohere.embed-multilingual-v3"]


VALID_EMBEDDING_MODELS = {
    "openai": {"text-embedding-3-large", "text-embedding-3-small", "text-embedding-ada-002"},
    "local": {"facebook/contriever", "intfloat/multilingual-e5-large"},
    "bedrock": {"amazon.titan-embed-text-v2:0", "cohere.embed-multilingual-v3"},
}

Job: TypeAlias = Literal["file_expiration"]

logger = get_logger(__name__)

_llm_cache = defaultdict(dict)


def assert_never(arg: Never) -> Never:
    msg = f"Expected code to be unreachable: {arg}"
    raise AssertionError(msg)


class Settings(BaseSettings):
    oauth_secret_key: SecretStr
    oauth_algorithm: str = "HS256"
    oauth_token_expire_minutes: int = 60 * 24

    chunk_size: int = 1000
    chunk_overlap: int = 100
    top_k: int

    default_llm_temperature: float = 0.01
    default_llm_provider: LLMProvider = LLMProvider.OPENAI
    alpha: float = 0.5
    default_llm_max_tokens: int = 800
    default_llm_top_p: float = 0.95
    default_llm_context_length: int = 0

    request_timeout: float = 60

    openai_llm_model: OpenAIModel = "gpt-4o"
    openai_embedding_model: OpenAIEmbeddingModel = "text-embedding-3-small"
    openai_api_key: SecretStr = SecretStr("")

    bedrock_llm_model: str = "mistral.mixtral-8x7b-instruct-v0:1"
    bedrock_embedding_model: str = "amazon.titan-embed-text-v2:0"
    aws_default_region: str
    aws_access_key_id: str
    aws_secret_access_key: SecretStr

    local_llm_model: OllamaModel = "llama3.1:8b"
    local_embedding_model: LocalEmbeddingModel | str = "facebook/contriever"
    local_models_only: bool = False
    local_embedding_device: str = "cpu"
    ollama_url: str = "http://localhost:11434"

    embedding_mode: LLMProvider

    weaviate_host: str = "localhost"
    weaviate_port: int = 8080
    weaviate_grpc_host: str = "localhost"
    weaviate_grpc_port: int = 50051
    weaviate_index: str
    weaviate_api_key: SecretStr = SecretStr("skillbyte")

    db_user: str = "postgres"
    db_password: SecretStr = SecretStr("postgres")
    db_host: str = "localhost"
    db_port: int = 5432
    db_database_name: str
    db_connection_pool_size: int = 10

    langchain_db_user: str = "postgres"
    langchain_db_password: SecretStr = SecretStr("postgres")
    langchain_db_host: str = "localhost"
    langchain_db_port: int = 5432
    langchain_db_database_name: str
    rate_limit: str = "5/minute"

    mlflow_tracking_token: str = ""

    @property
    def db_connection_string(self) -> str:
        return f"postgresql+psycopg2://{self.db_user}:{self.db_password.get_secret_value()}@{self.db_host}:{self.db_port}/{self.db_database_name}"

    @property
    def langchain_db_connection_string(self) -> str:
        return f"postgresql+psycopg2://{self.langchain_db_user}:{self.langchain_db_password.get_secret_value()}@{self.langchain_db_host}:{self.langchain_db_port}/{self.langchain_db_database_name}"

    object_store_endpoint_url: str
    object_store_secure: bool = True
    object_store_access_key_id: str
    object_store_secret_access_key: SecretStr
    object_store_files_bucket_name: str
    object_store_auto_create_buckets: bool = True

    langfuse_host: str
    langfuse_public_key: str
    langfuse_secret_key: SecretStr

    app_host: str
    app_port: int
    app_version: str = "dev"
    admin_name: str = "Admin"
    system_language: str = "German"

    environment: str = "dev"

    title_max_length: int = 300

    spending_limit_input_tokens_initial_value: int = 1_000_000
    spending_limit_output_tokens_initial_value: int = 1_000_000

    num_document_indexer_threads: int = Field(default=1, ge=0)
    num_document_converter_threads: int = Field(default=1, ge=0)

    gotenberg_url: str = "http://gotenberg:3100"

    job: Job | None = None
    all_users_group_name: str = "Alle"

    def llm(self, llm_option: LLM) -> RunnableSerializable:
        sub_cache = _llm_cache["chat"]
        if llm_option.id not in sub_cache:
            # caching by ID is probably not what we want, since when the model settings are changed without a new ID, the old settings are used until app restart
            sub_cache[llm_option.id] = self._llm(llm_option)
        return sub_cache[llm_option.id]

    def _llm(self, llm_option: LLM) -> RunnableSerializable:
        model_name = llm_option.llm_model_name
        temperature = llm_option.temperature
        max_tokens = llm_option.max_tokens
        top_p = llm_option.top_p
        context_length = llm_option.context_length
        match llm_option.provider:
            case LLMProvider.BEDROCK:
                return ChatBedrockConverse(
                    region_name=llm_option.aws_region or self.aws_default_region,
                    model=model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                ).with_retry(wait_exponential_jitter=True, stop_after_attempt=3)  # type: ignore[reportReturnType]
            case LLMProvider.OPENAI:
                return ChatOpenAI(
                    api_key=self.openai_api_key,
                    model=model_name,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                    timeout=self.request_timeout,
                    stream_usage=True,
                )
            case LLMProvider.LOCAL:
                return Ollama(
                    base_url=self.ollama_url,
                    model=model_name,
                    temperature=temperature,
                    top_p=top_p,
                    num_ctx=context_length,
                    num_predict=max_tokens,
                    timeout=int(self.request_timeout),
                )
            case None:
                raise RuntimeError
            case _:
                assert_never(llm_option)
                return None

    def title_llm(self, llm_option: LLM) -> RunnableSerializable:
        sub_cache = _llm_cache["title"]
        if llm_option.id not in sub_cache:
            sub_cache[llm_option.id] = self._title_llm(llm_option)
        return sub_cache[llm_option.id]

    def _title_llm(self, llm_option: LLM) -> RunnableSerializable:
        model_name = llm_option.title_model_name
        temperature = llm_option.title_temperature
        match llm_option.provider:
            case LLMProvider.BEDROCK:
                return ChatBedrockConverse(
                    model=model_name,
                    region_name=llm_option.aws_region or self.aws_default_region,
                    temperature=temperature,
                )
            case LLMProvider.OPENAI:
                return ChatOpenAI(
                    api_key=self.openai_api_key,
                    model=model_name,
                    temperature=temperature,
                    timeout=self.request_timeout,
                )
            case LLMProvider.LOCAL:
                return Ollama(
                    base_url=self.ollama_url,
                    model=model_name,
                    temperature=temperature,
                    timeout=int(self.request_timeout),
                )
            case None:
                raise RuntimeError
            case _:
                assert_never(llm_option)
                return None

    # TODO not only cache this but warm this up in main.py so that initial invocation is fast, especially for local embedding
    @cached_property
    def embed_model(self) -> Embeddings:
        match self.embedding_mode:
            case LLMProvider.BEDROCK:
                logger.info("using embeddings from Amazon Bedrock")
                return BedrockEmbeddings(
                    client=None,
                    model_id=self.bedrock_embedding_model,
                )
            case LLMProvider.OPENAI:
                logger.info("using embeddings from OpenAI")
                return OpenAIEmbeddings(
                    api_key=self.openai_api_key,
                    model=self.openai_embedding_model,
                    chunk_size=self.chunk_size,
                    timeout=self.request_timeout,
                )
            case LLMProvider.LOCAL:
                try:
                    import torch  # type: ignore[reportMissingImports]
                    from langchain_huggingface import HuggingFaceEmbeddings  # type: ignore[reportMissingImports]
                except ImportError:
                    print("Please install the 'local' dependency group")
                    raise

                device = os.getenv("LOCAL_EMBEDDING_DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu")
                logger.info("using local embeddings with device %s", device)
                local_files_only = settings.local_models_only
                if not local_files_only:
                    logger.info("allowing automatic download from huggingfaces")
                return HuggingFaceEmbeddings(
                    model_name=self.local_embedding_model,
                    model_kwargs={"device": device, "local_files_only": local_files_only},
                )
            case mode:
                assert_never(mode)
                return None

    def get_spending_limit(self, spending_limit_type: SpendingLimitType) -> int:
        match spending_limit_type:
            case SpendingLimitType.INPUT_TOKEN:
                return self.spending_limit_input_tokens_initial_value
            case SpendingLimitType.OUTPUT_TOKEN:
                return self.spending_limit_output_tokens_initial_value
            case mode:
                assert_never(mode)
                return None

    model_config = SettingsConfigDict(env_file=Path(".env"), env_file_encoding="utf-8", extra="ignore")


class AdminSettings(BaseSettings):
    # Default values and fields
    default_llm_display_name: Annotated[str, FieldPydantic(max_length=128)]
    default_llm_provider: LLMProvider
    default_llm_model_name: str
    default_llm_title_model_name: str
    default_llm_temperature: Annotated[float, FieldPydantic(ge=0, le=1)]
    default_llm_title_temperature: Annotated[float, FieldPydantic(ge=0, le=1)]
    default_llm_max_tokens: Annotated[int, FieldPydantic(ge=0)]
    default_llm_top_p: Annotated[float, FieldPydantic(ge=0, le=1)]
    default_llm_context_length: Annotated[int, FieldPydantic(ge=0)]

    # Weaviate and Embedding Settings
    embedding_provider: LLMProvider
    embedding_model: str
    weaviate_index_prefix: Annotated[str, FieldPydantic(max_length=64)]

    @field_validator("embedding_model")
    def validate_embedding_model(cls, v: str, info: FieldValidationInfo) -> str:  # noqa: N805
        provider = info.data.get("embedding_provider")
        if provider and v not in VALID_EMBEDDING_MODELS.get(provider, set()):
            raise NotValidProviderModelError()  # noqa: RSE102
        return v

    @field_validator("weaviate_index_prefix")
    def validate_weaviate_index_name(cls, v: str) -> str:  # noqa: N805
        return re.sub(r"[-/:.+&@#!%^*()=\\|\'\"?[\],{}<>$~]", "_", v)

    def to_admin_setting_list(self) -> list[AdminSetting]:
        admin_settings = []
        for k, v in self.model_dump().items():
            admin_settings.append(AdminSetting(key=k, value=str(v)))
        return admin_settings

    def to_db(self, session: Session) -> None:
        for setting in self.to_admin_setting_list():
            db_obj = session.get(AdminSetting, setting.key)
            if db_obj is None:
                session.add(setting)
            else:
                db_obj.value = setting.value
                session.add(db_obj)
        session.commit()

    @classmethod
    def from_admin_setting_list(cls, admin_settings: Iterable[AdminSetting]) -> "AdminSettings":
        return cls(**{it.key: it.value for it in admin_settings})  # type: ignore[reportReturnType]

    @classmethod
    def from_db(cls, session: Session) -> "AdminSettings":
        return cls.from_admin_setting_list(session.exec(select(AdminSetting)))

    @property
    def namespace(self) -> str:
        updated_model_name = re.sub(r"[-/:.]", "_", self.embedding_model)
        return f"{self.weaviate_index_prefix}_{self.embedding_provider}_{updated_model_name}"


def get_admin_settings(session: Annotated[Session, Depends(db_engine.get_session)]) -> AdminSettings:
    return AdminSettings.from_db(session)


load_dotenv()
settings = Settings()  # type: ignore[reportCallIssue]


def get_limiter() -> Limiter:
    return Limiter(key_func=get_remote_address)


limiter = get_limiter()
