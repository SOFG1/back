from datetime import UTC, datetime
from operator import itemgetter
from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableAssign, RunnablePassthrough, RunnableSerializable
from sqlmodel import Session
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import _Filters

from app.api.models import Conversation, File, UserId
from app.api.routers.files import get_user_files_by_file_ids
from app.engine.index import get_retriever
from app.settings import Settings
from custom_prompts import (
    CONDENSE_PROMPT_TEMPLATE,
    CONTEXT_PROMPT_TEMPLATE_WITH_CITATIONS,
    CONTEXT_PROMPT_TEMPLATE_WITHOUT_CITATIONS,
    SYSTEM_PROMPT,
)


class Input(TypedDict):
    chat_history: list[BaseMessage]
    question: str


class Chains:
    def __init__(
        self, llm: RunnableSerializable, session: Session | None = None, chatbot_owner_id: UserId | None = None
    ) -> None:
        self.retriever_chain: RunnableAssign
        self.llm = llm

        self._session = session
        self._chatbot_owner_id = chatbot_owner_id

    @staticmethod
    def get_filters(allowed_files: list[File] | None = None) -> _Filters:
        if not allowed_files:
            return Filter.by_property("file_id").equal("00000000-0000-0000-0000-000000000000")
        return Filter.any_of([Filter.by_property("file_id").equal(str(file.id)) for file in allowed_files])

    def process_docs(self, docs: list[Document]) -> str:
        if self._chatbot_owner_id and self._session:
            file_users = get_user_files_by_file_ids(
                session=self._session,
                file_owner_id=self._chatbot_owner_id,
                file_ids=[doc.metadata["file_id"] for doc in docs],
            )
            file_mapping = {str(file_user.file.id): file_user for file_user in file_users}
        else:
            file_mapping = {}
        formatted_docs = []
        for idx, doc in enumerate(docs, start=1):
            file_id = str(doc.metadata["file_id"])
            if file_mapping and file_id in file_mapping:
                file_user = file_mapping[file_id]
                file_name = file_user.file_name
                doc.metadata.update(
                    {
                        "file_name": file_name,
                        "file_user_id": file_user.id,
                        "file_size": file_user.file.file_size,
                        "file_url": file_user.url,
                    }
                )
            else:
                file_name = file_id
            formatted_docs.append(f"<context id='{idx}' file-name='{file_name}'>\n{doc.page_content}\n</context>\n")
        return "\n\n".join(formatted_docs)

    def get_rewrite_question_chain(self, chat_history: list[BaseMessage]) -> RunnableSerializable:  # noqa: ARG002
        # TODO: chat_history is not used?
        refinement_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", CONDENSE_PROMPT_TEMPLATE),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{question}"),
            ],
        )
        return refinement_prompt | self.llm | StrOutputParser()

    def contextualized_question(self, input: Input) -> RunnableSerializable | str:
        if chat_history := input.get("chat_history"):
            return self.get_rewrite_question_chain(chat_history)
        return input["question"]

    def get_conversational_chain(
        self, settings: Settings, db_conversation: Conversation | None = None
    ) -> RunnableSerializable:
        system_prompt = (
            db_conversation.chatbot.system_prompt
            if db_conversation and db_conversation.chatbot and db_conversation.chatbot.system_prompt
            else SYSTEM_PROMPT
        )
        if db_conversation and db_conversation.chatbot and db_conversation.citation_mode:
            context_prompt = CONTEXT_PROMPT_TEMPLATE_WITH_CITATIONS
        else:
            context_prompt = CONTEXT_PROMPT_TEMPLATE_WITHOUT_CITATIONS

        combined_prompt = "<system_prompt>\n" + system_prompt + "\n</system_prompt>" + "\n\n" + context_prompt

        qa_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", combined_prompt),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{question}"),
            ],
        )

        filters = None
        if db_conversation and db_conversation.chatbot is not None:
            filters = self.get_filters(
                [
                    file.file
                    for file in db_conversation.chatbot.files
                    if not file.expires or file.expires.astimezone(tz=UTC) >= datetime.now(tz=UTC)
                ]
            )
        retriever = get_retriever(settings, filters)

        # self.retriever_chain = RunnablePassthrough.assign(context=self.contextualized_question | retriever)

        generation_chain = (
            RunnablePassthrough.assign(context=lambda x: self.process_docs(x["sources"]))
            | qa_prompt
            | self.llm
            | StrOutputParser()
        )

        return {
            "sources": self.contextualized_question | retriever,
            "date": itemgetter("date"),
            "chatbot_name": itemgetter("chatbot_name"),
            "chat_history": itemgetter("chat_history"),
            "question": itemgetter("question"),
        } | RunnablePassthrough.assign(output=generation_chain)
