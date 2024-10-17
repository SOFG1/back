import json
from collections.abc import Sequence

from langchain_core.documents import Document
from typing_extensions import TypedDict


class Output(TypedDict):
    file_id: str
    file_user_id: str
    file_url: str
    page: int
    file_name: str
    file_size: int
    source: str
    context_content: str


def get_sorted_resource_list(
    documents: Sequence[Document],
) -> list[Output]:
    return [
        {
            "file_id": str(document.metadata["file_id"]),
            "file_user_id": str(document.metadata["file_user_id"]),
            "file_url": document.metadata["file_url"],
            "page": int(document.metadata["page"]),
            "file_name": document.metadata["file_name"],
            "file_size": document.metadata["file_size"],
            "source": document.metadata["source"],
            "context_content": document.page_content,
        }
        for document in documents
    ]


def convert_to_json(documents: list[Document]) -> str:
    return json.dumps({"citations": get_sorted_resource_list(documents)}, ensure_ascii=False)
