from pathlib import Path
from unittest.mock import Mock

from langchain_core.documents import Document
from sqlmodel import Session

from app.api.models import UserPublic
from app.engine.chains import Chains
from tests.conftest import AddFile


def test_chains_process_docs(db_session: Session, fake_user: UserPublic, add_file: AddFile) -> None:
    public_file_1 = add_file(
        path=Path("data/testdocs/1-die-ersten-news.md.pdf"), user=fake_user, file_name="first-news.pdf"
    )
    public_file_2 = add_file(
        path=Path("data/testdocs/2-newsletter-nr-2.md.pdf"), user=fake_user, file_name="second-news.pdf"
    )

    docs = []
    for idx, file_obj in enumerate([public_file_1, public_file_2], start=1):
        doc = Document(page_content=f"mocked {idx} file")
        doc.metadata["file_id"] = str(file_obj.file.id)
        docs.append(doc)

    chains = Chains(
        llm=Mock(),
        session=db_session,
        chatbot_owner_id=fake_user.id,
    )

    assert chains.process_docs(docs=[]) == ""

    assert chains.process_docs(docs=docs) == (
        "<context id='1' file-name='first-news.pdf'>\nmocked 1 file\n</context>\n\n\n"
        "<context id='2' file-name='second-news.pdf'>\nmocked 2 file\n</context>\n"
    )

    # test side effect
    assert docs[0].metadata == {
        "file_id": str(public_file_1.file.id),
        "file_user_id": public_file_1.id,
        "file_name": public_file_1.file_name,
        "file_size": public_file_1.file.file_size,
        "file_url": f"/api/files/download/{public_file_1.id}/first-news.pdf",
    }
