from uuid import UUID

from weaviate.classes.query import Filter

from app.engine.client_getter import get_weaviate_client
from app.settings import settings


def remove_file_from_vectordb(file_id: UUID) -> None:
    client = get_weaviate_client()
    collection = client.collections.get(settings.weaviate_index)
    collection.data.delete_many(where=Filter.by_property("file_id").equal(str(file_id)))
    client.close()


def clear_vectordb(index_name: str = settings.weaviate_index) -> None:
    client = get_weaviate_client()
    client.collections.delete(index_name)
    client.close()


if __name__ == "__main__":
    clear_vectordb()
