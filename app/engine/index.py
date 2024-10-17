from langchain_core.vectorstores import VectorStoreRetriever
from langchain_weaviate.vectorstores import WeaviateVectorStore
from weaviate import WeaviateClient
from weaviate.classes.config import DataType, Property
from weaviate.collections.classes.filters import _Filters

from app.custom_logging import get_logger
from app.engine.client_getter import get_weaviate_client
from app.settings import Settings

logger = get_logger(__name__)


def _weaviate_store_and_client(settings: Settings) -> tuple[WeaviateClient, WeaviateVectorStore]:
    client = get_weaviate_client()
    store = WeaviateVectorStore(
        client=client,
        index_name=settings.weaviate_index,
        embedding=settings.embed_model,
        text_key="text",
    )

    cls = client.collections.get(settings.weaviate_index)
    properties = cls.config.get(simple=False).properties.copy()

    if not any(prop.name == "file_id" for prop in properties):
        cls.config.add_property(
            Property(
                name="file_id",
                data_type=DataType.TEXT,
                index_filterable=True,
                index_searchable=True,
            )
        )
        logger.info("vectordb didn't contain file_id property, created.")

    return client, store


def cold_start_vector_db(settings: Settings) -> None:
    logger.info("Start first WeaviateDB ...")
    client, _ = _weaviate_store_and_client(settings=settings)
    logger.info("Finish start WeaviateDB.")
    client.close()


def get_retriever(settings: Settings, file_filter: _Filters | None) -> VectorStoreRetriever:
    logger.info("Connecting to index from WeaviateDB...")
    _, store = _weaviate_store_and_client(settings=settings)
    logger.info("Finished connecting to index from WeaviateDB.")
    return store.as_retriever(search_kwargs={"filters": file_filter, "k": settings.top_k})
