import weaviate
from weaviate.auth import Auth

from app.settings import settings


def get_weaviate_client() -> weaviate.WeaviateClient:
    return weaviate.connect_to_custom(
        http_host=settings.weaviate_host,
        http_port=settings.weaviate_port,
        http_secure=False,
        grpc_host=settings.weaviate_grpc_host,
        grpc_port=settings.weaviate_grpc_port,
        grpc_secure=False,
        auth_credentials=Auth.api_key(settings.weaviate_api_key.get_secret_value()),
    )
