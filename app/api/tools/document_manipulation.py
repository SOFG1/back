from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.api.models import File
from app.custom_logging import get_logger
from app.engine.object_store import object_store
from app.settings import settings

logger = get_logger(__name__)


def get_docs_with_text(file: File) -> list[Document]:
    logger.info("loading %s from object store", file.path)
    assert file.pdf_path
    file_path = object_store.get_object_locally(settings.object_store_files_bucket_name, file.pdf_path)
    try:
        logger.info("running PyMuPDFLoader for local file %s", file_path)
        return [doc for doc in PyMuPDFLoader(file_path=file_path, extract_images=False).load()]
    finally:
        object_store.delete_local_file(file_path)
        logger.info("deleted temporary file %s", file_path)


def chunk_documents(file: File) -> list[Document]:
    docs = get_docs_with_text(file)
    logger.info("got %d documents for %s", len(docs), file.id)
    for page, doc in enumerate(docs, 1):
        doc.metadata["file_id"] = str(file.id)
        doc.metadata["page"] = page
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        length_function=len,
    ).split_documents([doc for doc in docs if doc.page_content])
