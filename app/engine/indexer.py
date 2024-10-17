import threading
import time

from langchain.indexes import SQLRecordManager, index
from langchain_weaviate import WeaviateVectorStore
from sqlalchemy_utils import create_database, database_exists
from sqlmodel import col, select

from app.api.models import File, IndexingStatus
from app.api.tools.db import db_engine
from app.api.tools.document_manipulation import chunk_documents
from app.custom_logging import get_logger
from app.engine.client_getter import get_weaviate_client
from app.settings import settings


class Indexer:
    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__)
        self.index: str | None = None
        self.store: WeaviateVectorStore | None = None
        self.record_manager: SQLRecordManager | None = None
        self._running = True
        self.threads: list[threading.Thread] = []

    def initialize(self, new_index: str) -> None:
        self.logger.info("Initializing indexer for namespace: %s", new_index)
        self.index = new_index
        self.store = WeaviateVectorStore(
            client=get_weaviate_client(),
            index_name=self.index,
            embedding=settings.embed_model,
            text_key="text",
        )
        namespace = "weaviate/"
        db_url = settings.langchain_db_connection_string
        if not database_exists(db_url):
            create_database(db_url)
        self.record_manager = SQLRecordManager(namespace, db_url=db_url)
        self.record_manager.create_schema()
        self.logger.info("Initialization complete.")

    def start(self) -> None:
        self.threads = []
        self._running = True
        for i in range(settings.num_document_indexer_threads):
            self.threads.append(threading.Thread(target=self.poll_continuously, name=f"indexer-{i}", daemon=True))
            self.threads[-1].start()

    def stop(self) -> None:
        self.logger.info("Stopping indexer...")
        self._running = False
        for thread in self.threads:
            if thread.is_alive():
                thread.join()
        self.logger.info("All threads have been stopped.")

    def poll_continuously(self) -> None:
        self.logger.info("Starting continuous poll.")
        while self._running:
            try:
                self.poll()
            except Exception:
                self.logger.exception("Polling loop crashed, restarting.")
                time.sleep(5)

    def poll(self) -> None:
        with db_engine.get_session_raw() as session:
            # with_for_update locks the row so other instances of this indexer can't access it.
            # skip_locked skips those locked rows, so other instances don't block but process other files.
            # in case this code dies, postgres automatically unlocks the row.
            file = session.exec(
                select(File)
                .where(File.indexing_status == IndexingStatus.PENDING, col(File.pdf_path).isnot(None))
                .with_for_update(skip_locked=True)
                .limit(1)
            ).one_or_none()

            if file is None:
                time.sleep(5)
                return

            try:
                self.logger.info("indexing file %s", file.id)
                documents = chunk_documents(file)
                assert self.store is not None
                assert self.record_manager
                index(
                    docs_source=documents,
                    vector_store=self.store,
                    record_manager=self.record_manager,
                    cleanup=None,
                )
                self.logger.info(
                    "Successfully created embeddings for file %s in the Weaviate collection %s",
                    file.id,
                    self.index,
                )
                file.indexing_status = IndexingStatus.INDEXED
                file.indexing_error = None
            except Exception as e:
                self.logger.exception("failed to index file %s", file.id)
                file.indexing_status = IndexingStatus.FAILED
                file.indexing_error = repr(e)
            session.add(file)
            session.commit()


indexer = Indexer()

if __name__ == "__main__":
    get_weaviate_client().collections.delete_all()
