import sys
import tempfile
from pathlib import Path
from typing import BinaryIO

from minio import Minio
from minio.deleteobjects import DeleteObject

from app.custom_logging import get_logger
from app.settings import settings


class ObjectStore:
    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__)
        self.client: Minio | None = None

    def create_client(
        self,
        object_store_endpoint_url: str,
        object_store_access_key_id: str,
        object_store_secret_access_key: str,
        object_store_secure: bool = True,  # noqa: FBT001, FBT002
    ) -> None:
        self.logger.info("connecting to %s", object_store_endpoint_url)
        self.client = Minio(
            object_store_endpoint_url,
            access_key=object_store_access_key_id,
            secret_key=object_store_secret_access_key,
            secure=object_store_secure,
        )

    def create_bucket_if_not_exists(self, bucket_name: str) -> None:
        assert self.client
        if not self.client.bucket_exists(bucket_name):
            self.logger.info("bucket %s does not exist", bucket_name)
            self.client.make_bucket(bucket_name)
            self.logger.info("bucket %s created", bucket_name)

    def store_object(self, bucket_name: str, object_name: str, content: BinaryIO) -> None:
        self.logger.info("storing object %s in bucket %s", object_name, bucket_name)
        assert self.client
        self.client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=content,
            length=-1,
            part_size=10 * 1024 * 1024,
        )

    def get_object(self, bucket_name: str, object_name: str) -> bytes:
        assert self.client
        self.logger.info("retrieving %s from bucket %s", object_name, bucket_name)
        resp = self.client.get_object(bucket_name=bucket_name, object_name=object_name)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    # Only use this in conjunction with delete_local_file for when you have to have a file locally.
    # The files created through this are not persistent.
    # Keep the amount of time and the quantity and size of local files small.
    # Delete them as soon as not needed anymore.
    def get_object_locally(self, bucket_name: str, object_name: str) -> str:
        with tempfile.NamedTemporaryFile(delete=False) as f:
            self.logger.info("storing %s from bucket %s locally in %s", object_name, bucket_name, f.name)
            assert self.client
            self.client.fget_object(
                bucket_name=bucket_name,
                object_name=object_name,
                file_path=f.name,
            )
            return f.name

    def delete_local_file(self, file_path: str) -> None:
        self.logger.info("deleting %s", file_path)
        Path(file_path).unlink()

    def delete_object(self, bucket_name: str, object_name: str) -> None:
        assert self.client
        self.logger.info("deleting object %s from bucket %s", object_name, bucket_name)
        self.client.remove_object(bucket_name=bucket_name, object_name=object_name)

    def empty_bucket(self, bucket_name: str) -> None:
        if "pytest" not in sys.modules:
            msg = "only ever run this in tests"
            raise RuntimeError(msg)
        assert self.client
        if not self.client.bucket_exists(bucket_name):
            self.logger.info("tried to empty bucket %s, bucket doesn't exist", bucket_name)
            return
        self.logger.info("removing all objects from bucket %s", bucket_name)
        for error in self.client.remove_objects(
            bucket_name=bucket_name,
            delete_object_list=[
                DeleteObject(name=x.object_name)
                for x in self.client.list_objects(bucket_name=bucket_name, recursive=True)
                if x.object_name is not None
            ],
        ):
            self.logger.error(error)

    def check_health(self) -> None:
        assert self.client
        self.client.bucket_exists(settings.object_store_files_bucket_name)


object_store = ObjectStore()
