import os
from pathlib import Path
import re
from datetime import datetime
from typing import Any
from langchain_community.callbacks import get_openai_callback
import mlflow
import requests
from datasets import Dataset
from dotenv import load_dotenv
from git import Repo
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.indexing import index
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from mlflow.exceptions import RestException
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    answer_similarity,
    context_entity_recall,
    context_precision,
    context_recall,
    faithfulness,
    answer_correctness,
    context_utilization,
)

from app.api.models import LLMProvider, LLM
from app.engine.chains import Chains
from app.engine.file_remover import clear_vectordb
from app.engine.indexer import Indexer
from app.settings import settings, assert_never
from evaluation.eval_queries import GROUND_TRUTH, QUERIES

load_dotenv()

embedding_model = {
    LLMProvider.LOCAL: settings.local_embedding_model,
    LLMProvider.OPENAI: settings.openai_embedding_model,
    LLMProvider.BEDROCK: settings.bedrock_embedding_model,
}
settings.weaviate_index = f"default_{settings.embedding_mode}_{embedding_model[settings.embedding_mode]}".replace(
    "-", "_"
)


def get_git_info() -> dict[str, str | None]:
    try:
        repo = Repo(".")  # Initialize a Repo object for the current directory
        # Get the current commit hash
        current_commit_hash = repo.head.commit.hexsha
        current_commit_message = str(repo.head.commit.message)

        # Get all tags and filter for semantic versions
        tags = repo.tags
        semantic_versioning_pattern = r"^v?(\d+)\.(\d+)\.(\d+)(?:-(.+))?$"  # Simple semantic version regex
        semantic_tags = [tag for tag in tags if re.match(semantic_versioning_pattern, tag.name)]

        # If we found semantic version tags, get the latest one
        if semantic_tags:
            latest_tag = max(semantic_tags, key=lambda t: t.commit.committed_datetime)
            latest_version = latest_tag.name
        else:
            latest_version = None

    except Exception as e:
        print(f"Error getting Git information: {e}")
        current_commit_hash = None
        latest_version = None
        current_commit_message = None

    return {"commit_hash": current_commit_hash, "latest_version": latest_version, "message": current_commit_message}


def get_gitlab_username(access_token: str) -> str | None:
    url = "https://gitlab.com/api/v4/user"  # Endpoint to get user information
    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    response = requests.get(url, headers=headers)  # noqa: S113

    if response.status_code == 200:
        user_info = response.json()
        return user_info.get("username")
    print(f"Failed to retrieve user info: {response.status_code} - {response.text}")
    return None


def get_tags() -> dict[str, Any] | None:
    tags = {}

    git_info = get_git_info()
    commit_hash = git_info["commit_hash"]
    assert commit_hash
    tags["mlflow.source.git.commit"] = commit_hash
    if git_info["latest_version"]:
        tags["gitlab.version"] = git_info["latest_version"]

    user_name = get_gitlab_username(settings.mlflow_tracking_token)
    if user_name:
        tags["mlflow.user"] = f"@{user_name}"

    if os.getenv("GITLAB_CI"):
        tags["gitlab.CI_JOB_ID"] = os.getenv("CI_JOB_ID")

    if git_info["message"]:
        tags["message"] = git_info["message"]

    return tags or None


def chunk_documents(directory_path: str) -> list:
    chunks = []

    # Iterate over all files in the directory
    for file_path in Path(directory_path).iterdir():
        # Load the document
        docs = [doc for doc in PyMuPDFLoader(file_path=str(file_path.absolute()), extract_images=False).load()]

        # Add metadata to each document
        for page, doc in enumerate(docs, 1):
            doc.metadata["page"] = page

        # Split documents into chunks
        chunks.extend(
            RecursiveCharacterTextSplitter(
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
                length_function=len,
            ).split_documents([doc for doc in docs if doc.page_content])
        )

    return chunks


def get_dataset_from_csv(dataset_path: str) -> Dataset:
    return Dataset.from_csv(dataset_path)


def extend_dataset(dataset: Dataset, llm_options: LLM) -> Dataset:
    """Extends the Dataset with llm answers and retrieved contexts"""
    data_dict = dataset.to_dict()
    assert isinstance(data_dict, dict)
    data_dict["answer"] = []
    data_dict["contexts"] = []
    chain = Chains(settings.llm(llm_options))
    chat_engine = chain.get_conversational_chain(settings, db_conversation=None)

    answers = chat_engine.batch(
        [
            {
                "question": question,
                "chat_history": [],
                "date": datetime.now().astimezone().isoformat(),
                "chatbot_name": "Test",
            }
            for question in data_dict["question"]
        ]
    )
    for answer in answers:
        data_dict["answer"].append(answer["output"])
        data_dict["contexts"].append([a.page_content for a in answer["sources"]])

    return Dataset.from_dict(data_dict)


def create_eval_vectorstore(index_name: str):
    docs = chunk_documents("evaluation/eval_pipeline_docs")
    indexer = Indexer()
    indexer.initialize(index_name)
    assert indexer.record_manager
    indexer.record_manager.delete_keys(indexer.record_manager.list_keys())
    assert indexer.store
    index(docs_source=docs, vector_store=indexer.store, record_manager=indexer.record_manager, cleanup=None)


def clear_vdb(index_name: str) -> None:
    indexer = Indexer()
    indexer.initialize(index_name)
    assert indexer.record_manager
    indexer.record_manager.delete_keys(indexer.record_manager.list_keys())
    clear_vectordb(index_name)


def create_llm(options: LLMProvider) -> LLM:
    match options:
        case LLMProvider.OPENAI:
            llm = LLM(
                display_name="openai",
                provider=options,
                llm_model_name=settings.openai_llm_model,
                title_model_name=settings.openai_llm_model,
                temperature=settings.default_llm_temperature,
                title_temperature=settings.default_llm_temperature,
                max_tokens=settings.default_llm_max_tokens,
                top_p=settings.default_llm_top_p,
                context_length=settings.default_llm_context_length,
            )
        case LLMProvider.BEDROCK:
            llm = LLM(
                display_name="bedrock",
                provider=options,
                llm_model_name=settings.bedrock_llm_model,
                title_model_name=settings.bedrock_llm_model,
                temperature=settings.default_llm_temperature,
                title_temperature=settings.default_llm_temperature,
                max_tokens=settings.default_llm_max_tokens,
                top_p=settings.default_llm_top_p,
                context_length=settings.default_llm_context_length,
            )
        case LLMProvider.LOCAL:
            llm = LLM(
                display_name="local",
                provider=options,
                llm_model_name=settings.local_llm_model,
                title_model_name=settings.local_llm_model,
                temperature=settings.default_llm_temperature,
                title_temperature=settings.default_llm_temperature,
                max_tokens=settings.default_llm_max_tokens,
                top_p=settings.default_llm_top_p,
                context_length=settings.default_llm_context_length,
            )
        case _:
            assert_never(options)
            return None
    return llm


def add_total_score(results: dict) -> dict:
    average_score = sum(results.values()) / len(results)
    results["total_score"] = round(average_score, 4)
    return results


def eval_script():
    experiment = mlflow.get_experiment_by_name("TSAI Eval")
    if experiment:
        experiment_id = experiment.experiment_id
    else:
        experiment_id = mlflow.create_experiment("TSAI Eval")

    mlflow.set_experiment(experiment_id=experiment_id)
    with mlflow.start_run():
        tags = get_tags()
        print(tags)

        llm_option = settings.default_llm_provider
        llm = create_llm(llm_option)

        mlflow.log_params(
            {
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
                "top_k": settings.top_k,
                "alpha": settings.alpha,
                "temperature": llm.temperature,
                "top_p": llm.top_p,
                "embedding_mode": settings.embedding_mode,
                "max_tokens": llm.max_tokens,
                "llm_context_length": llm.context_length,
                "embedding_model": embedding_model[settings.embedding_mode],
                "llm_model": llm.llm_model_name,
            }
        )

        create_eval_vectorstore(settings.weaviate_index)
        with get_openai_callback() as cb:
            dataset = extend_dataset(get_dataset_from_csv("evaluation/datasets/pipeline_data.csv"), llm)

            print("Got dataset, evaluating...")
            results = evaluate(
                dataset,
                metrics=[
                    faithfulness,
                    answer_relevancy,
                    context_recall,
                    context_precision,
                    context_entity_recall,
                    answer_similarity,
                    context_utilization,
                    answer_correctness,
                ],
                llm=ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key, timeout=240.0),
                embeddings=OpenAIEmbeddings(
                    api_key=settings.openai_api_key,
                    model=settings.openai_embedding_model,
                    chunk_size=settings.chunk_size,
                    timeout=settings.request_timeout,
                ),
            )
        print("results before formatting:\n")
        print(results)
        results = add_total_score(results)
        print("results after formatting:\n")
        print(results)

        mlflow.log_param("total_tokens", cb.total_tokens)
        mlflow.log_param("prompt_tokens", cb.prompt_tokens)
        mlflow.log_param("completion_tokens", cb.completion_tokens)

        for k, v in results.items():
            mlflow.log_metric(k, v)

        if tags:
            mlflow.set_tags(tags)

    clear_vdb(settings.weaviate_index)


if __name__ == "__main__":
    print(f"settings: {settings}")
    clear_vdb(settings.weaviate_index)
    eval_script()
