"""Converter between different file formats"""

import time
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile

from gotenberg_client import GotenbergClient
from gotenberg_client.options import PdfAFormat
from sqlmodel import col, select

from app.api.models import File, IndexingStatus
from app.api.routers.files import SupportedMimeTypes
from app.api.tools.db import db_engine
from app.custom_logging import get_logger
from app.engine.object_store import object_store
from app.settings import assert_never, settings


class Converter:
    def __init__(self) -> None:
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("initializing")

    def poll_continuously(self) -> None:
        self.logger.info("starting continuous poll")
        while True:
            try:
                self.poll()
            except Exception:
                self.logger.exception("polling loop crashed, restarting")
                time.sleep(5)

    def poll(self) -> None:
        # with_for_update locks the row so other instances of this indexer can't access it.
        # skip_locked skips those locked rows, so other instances don't block but process other files.
        # in case this code dies, postgres automatically unlocks the row.
        with db_engine.get_session_raw() as session:
            file = session.exec(
                select(File)
                .where(File.indexing_status == IndexingStatus.PENDING, col(File.pdf_path).is_(None))
                .with_for_update(skip_locked=True)
                .limit(1)
            ).one_or_none()

            if file is None:
                session.commit()
                time.sleep(5)
                return

            match SupportedMimeTypes(file.mime_type):
                case SupportedMimeTypes.PDF:
                    file.pdf_path = file.path
                case SupportedMimeTypes.DOCX:
                    self.logger.info("Converting DOCX to PDF.")
                    self._convert_docx_to_pdf(file)
                case mime_type:
                    assert_never(mime_type)
            session.add(file)

            session.commit()

    def _convert_docx_to_pdf(self, file: File) -> None:
        """Function which converts a DOCX file to PDF and persists it to storage"""
        # Try a conversion
        self.logger.info("Starting to convert file %s", file.id)
        try:
            with NamedTemporaryFile(delete=False, suffix=".docx") as fp:
                docx_file_bytes = object_store.get_object(settings.object_store_files_bucket_name, file.path)
                fp.write(docx_file_bytes)
                fp.close()

                with GotenbergClient(settings.gotenberg_url) as client, client.libre_office.to_pdf() as route:
                    response = route.pdf_format(pdf_format=PdfAFormat.A3b).convert(Path(fp.name)).run()
                file.pdf_path = f"data/uploads/{file.id}.pdf"
        except Exception as e:
            self.logger.exception("File id %s conversion failed.", file.id, exc_info=e)
            file.indexing_status = IndexingStatus.FAILED
            file.indexing_error = repr(e)
            return

        # Try persisting the converted file
        try:
            object_store.store_object(settings.object_store_files_bucket_name, file.pdf_path, BytesIO(response.content))
        except Exception as e:
            self.logger.exception("Error while storing file", exc_info=e)

        self.logger.info("Finished converting file %s", file.id)


converter = Converter()
