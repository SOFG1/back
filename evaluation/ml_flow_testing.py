import logging
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from datasets import Dataset
from dotenv import load_dotenv
from langchain_community.document_loaders import PyMuPDFLoader, DirectoryLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from ragas import evaluate
from ragas.metrics import (
    answer_correctness,
    answer_relevancy,
    answer_similarity,
    context_entity_recall,
    context_precision,
    context_recall,
    context_utilization,
    faithfulness,
)
from ragas.metrics.critique import harmfulness

from app.engine import Chains, get_retriever
from app.settings import settings, LLMProvider
from evaluation.eval_queries import GROUND_TRUTH, QUERIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

os.environ["OPENAI_API_KEY"] = "OPENAI_API_KEY"


def get_dataset_from_csv(dataset_path: Path) -> Dataset:
    return Dataset.from_csv(dataset_path)


def get_data_samples() -> dict[str, list[str]]:
    # Dictionary zur Speicherung der Daten anlegen
    data_samples = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": GROUND_TRUTH,
    }
    load_dotenv()
    chain = Chains(settings.llm(LLMProvider.OPENAI))
    retriever = get_retriever(settings, None)
    conv_chain = chain.get_conversational_chain(settings, None)

    # Daten dynamisch aus den Funktionen holen und im Dictionary speichern
    for id, question in enumerate(QUERIES):
        answer = conv_chain.invoke(
            {
                "question": question,
                "chat_history": [],
                "date": datetime.now().astimezone().isoformat(),
                "chatbot_name": "Evaluation",
            }
        )
        unfiltered_context = retriever.invoke(question)
        context = []
        for c in unfiltered_context:
            context.append(c.page_content.strip())
        data_samples["question"].append(question)
        data_samples["answer"].append(answer["output"])
        data_samples["contexts"].append(context)

    return data_samples


def calc_faithfulness(title_of_test: str, dataset: Dataset) -> None:
    """This measures the factual consistency of the generated answer
    against the given context. It is calculated from answer and
    retrieved context. The answer is scaled to (0,1) range. Higher the better.
    This metric is computed using the question, the context and the answer.

    Requires: dict {question: , answer: , contexts:
    """
    file_name = "faithfulness.csv"
    directory_path = Path(f"results/{title_of_test}")
    filepath = Path(f"{directory_path}/{file_name}")
    if filepath.exists():
        logger.error(f"Not executed: the file '{filepath}' already exists.")
        return
    dataset = dataset.remove_columns("ground_truth")
    score = evaluate(dataset, metrics=[faithfulness])
    frame = score.to_pandas()
    os.makedirs(directory_path, exist_ok=True)
    frame.to_csv(filepath, index=False)


def calc_answer_relevancy(title_of_test: str, dataset: Dataset) -> None:
    """The evaluation metric, Answer Relevancy, focuses on assessing
    how pertinent the generated answer is to the given prompt.
    A lower score is assigned to answers that are incomplete or contain
    redundant information and higher scores indicate better relevancy.
    This metric is computed using the question, the context and the answer.

    Requires: dict {question: , answer: , contexts:
    """
    file_name = "answer_relevancy.csv"
    directory_path = Path(f"results/{title_of_test}")
    filepath = Path(f"{directory_path}/{file_name}")
    if filepath.exists():
        logger.error(f"Not executed: the file '{filepath}' already exists.")
        return
    dataset = dataset.remove_columns("ground_truth")
    score = evaluate(dataset, metrics=[answer_relevancy])
    frame = score.to_pandas()
    os.makedirs(directory_path, exist_ok=True)
    frame.to_csv(filepath, index=False)


def calc_context_recall(title_of_test: str, dataset: Dataset) -> None:
    """Context recall measures the extent to which the retrieved context aligns
    with the annotated answer, treated as the ground truth. It is computed
    based on the ground truth and the retrieved context, and the values range
    between 0 and 1, with higher values indicating better performance.

    To estimate context recall from the ground truth answer, each sentence in
    the ground truth answer is analyzed to determine whether it can be attributed
    to the retrieved context or not. In an ideal scenario, all sentences in the
    ground truth answer should be attributable to the retrieved context.

    Requires: dict {question: , answer: , contexts: , ground_truth:
    """
    file_name = "context_recall.csv"
    directory_path = Path(f"results/{title_of_test}")
    filepath = Path(f"{directory_path}/{file_name}")
    if filepath.exists():
        logger.error(f"Not executed: the file '{filepath}' already exists.")
        return

    score = evaluate(dataset, metrics=[context_recall])
    frame = score.to_pandas()
    os.makedirs(directory_path, exist_ok=True)
    frame.to_csv(filepath, index=False)


def calc_context_precision(title_of_test: str, dataset: Dataset) -> None:
    """Context Precision is a metric that evaluates whether all of the ground-truth
    relevant items present in the contexts are ranked higher or not. Ideally all the
    relevant chunks must appear at the top ranks. This metric is computed using the
    question, ground_truth and the contexts, with values ranging between 0 and 1,
    where higher scores indicate better precision.

    Requires: dict {question: , answer: , contexts: , ground_truth:
    """
    file_name = "context_precision.csv"
    directory_path = Path(f"results/{title_of_test}")
    filepath = Path(f"{directory_path}/{file_name}")
    if filepath.exists():
        logger.error(f"Not executed: the file '{filepath}' already exists.")
        return

    score = evaluate(dataset, metrics=[context_precision])
    frame = score.to_pandas()
    os.makedirs(directory_path, exist_ok=True)
    frame.to_csv(filepath, index=False)


def calc_context_utilization(title_of_test: str, dataset: Dataset) -> None:
    """This metric gauges the relevancy of the retrieved context, calculated based on
    both the question and contexts. The values fall within the range of (0, 1), with
    higher values indicating better relevancy.
                                                                                                    ###############
    Requires: dict {question: , contexts:}
    """
    file_name = "context_utilization.csv"
    directory_path = Path(f"results/{title_of_test}")
    filepath = Path(f"{directory_path}/{file_name}")
    if filepath.exists():
        logger.error(f"Not executed: the file '{filepath}' already exists.")
        return
    dataset = dataset.remove_columns(["ground_truth", "answer"])
    score = evaluate(dataset, metrics=[context_utilization])
    frame = score.to_pandas()
    os.makedirs(directory_path, exist_ok=True)
    frame.to_csv(filepath, index=False)


def calc_context_entity_recall(title_of_test: str, dataset: Dataset) -> None:
    """This metric gives the measure of recall of the retrieved context, based on the
    number of entities present in both ground_truths and contexts relative to the number
    of entities present in the ground_truths alone. Simply put, it is a measure of what
    fraction of entities are recalled from ground_truths. This metric is useful in
    fact-based use cases like tourism help desk, historical QA, etc. This metric can
    help evaluate the retrieval mechanism for entities, based on comparison with entities
    present in ground_truths, because in cases where entities matter, we need
    the contexts which cover them.

    Requires: dict {contexts: , ground_truth:
    """
    file_name = "context_entity_recall.csv"
    directory_path = Path(f"results/{title_of_test}")
    filepath = Path(f"{directory_path}/{file_name}")
    if filepath.exists():
        logger.error(f"Not executed: the file '{filepath}' already exists.")
        return
    dataset = dataset.remove_columns(["answer", "question"])
    score = evaluate(dataset, metrics=[context_entity_recall])
    frame = score.to_pandas()
    os.makedirs(directory_path, exist_ok=True)
    frame.to_csv(filepath, index=False)


def calc_answer_similarity(title_of_test: str, dataset: Dataset) -> None:
    """The concept of Answer Semantic Similarity pertains to the assessment of the semantic
    resemblance between the generated answer and the ground truth. This evaluation is
    based on the ground truth and the answer, with values falling within the range of 0 to 1.
    A higher score signifies a better alignment between the generated answer and the ground truth.

    Requires: dict {question: , answer: , ground_truth:
    """
    file_name = "answer_similarity.csv"
    directory_path = Path(f"results/{title_of_test}")
    filepath = Path(f"{directory_path}/{file_name}")
    if filepath.exists():
        logger.error(f"Not executed: the file '{filepath}' already exists.")
        return
    dataset = dataset.remove_columns("contexts")
    score = evaluate(dataset, metrics=[answer_similarity])
    frame = score.to_pandas()
    os.makedirs(directory_path, exist_ok=True)
    frame.to_csv(filepath, index=False)


def calc_answer_correctness(title_of_test: str, dataset: Dataset) -> None:
    """The assessment of Answer Correctness involves gauging the accuracy of the generated
    answer when compared to the ground truth. This evaluation relies on the ground truth and
    the answer, with scores ranging from 0 to 1. A higher score indicates a closer alignment
    between the generated answer and the ground truth, signifying better correctness.

    Requires: dict {question: , answer: , ground_truth:
    """
    file_name = "answer_correctness.csv"
    directory_path = Path(f"results/{title_of_test}")
    filepath = Path(f"{directory_path}/{file_name}")
    if filepath.exists():
        logger.error(f"Not executed: the file '{filepath}' already exists.")
        return
    dataset = dataset.remove_columns("contexts")
    score = evaluate(dataset, metrics=[answer_correctness])
    frame = score.to_pandas()
    os.makedirs(directory_path, exist_ok=True)
    frame.to_csv(filepath, index=False)


def calc_harmfulness(title_of_test: str, dataset: Dataset) -> None:
    """This is designed to assess submissions based on predefined aspects such as harmlessness
    and correctness. Additionally, users have the flexibility to define their own aspects for
    evaluating submissions according to their specific criteria. The output of aspect critiques
    is binary, indicating whether the submission aligns with the defined aspect or not.
    This evaluation is performed using the 'answer' as input.

    Requires: dict {question: , answer: , contexts:}
    """
    file_name = "harmlessness.csv"
    directory_path = Path(f"results/{title_of_test}")
    filepath = Path(f"{directory_path}/{file_name}")
    if filepath.exists():
        logger.error(f"Not executed: the file '{filepath}' already exists.")
        return
    dataset = dataset.remove_columns("ground_truth")
    score = evaluate(dataset, metrics=[harmfulness])
    frame = score.to_pandas()
    os.makedirs(directory_path, exist_ok=True)
    frame.to_csv(filepath, index=False)


def calc_all(title_of_test: str, description: str) -> None:
    directory_path = Path(f"results/{title_of_test}")
    if directory_path.exists():
        logger.error(f"Not executed: the folder '{directory_path}' already exists.")
        msg = f"Not executed: the folder '{directory_path}' already exists."
        raise FileExistsError(msg)
    data_samples = get_data_samples()
    dataset = Dataset.from_dict(data_samples)
    calc_faithfulness(title_of_test, dataset)
    calc_answer_relevancy(title_of_test, dataset)
    calc_context_recall(title_of_test, dataset)
    calc_context_precision(title_of_test, dataset)
    calc_context_utilization(title_of_test, dataset)
    calc_context_entity_recall(title_of_test, dataset)
    calc_answer_similarity(title_of_test, dataset)
    calc_answer_correctness(title_of_test, dataset)
    calc_harmfulness(title_of_test, dataset)

    # Write the description to a text file in the new directory
    description_file_path = directory_path / "description.txt"
    with open(description_file_path, "w") as file:
        file.write(description)
        logging.info(f"Description saved to {description_file_path}")


def calc_prompt_compare(title_of_test: str, description: str) -> None:
    directory_path = Path(f"results/prompt_tests/{title_of_test}")
    if directory_path.exists():
        logger.error(f"Not executed: the folder '{directory_path}' already exists.")
        msg = f"Not executed: the folder '{directory_path}' already exists."
        raise FileExistsError(msg)
    data_samples = get_data_samples()
    dataset = Dataset.from_dict(data_samples)
    calc_faithfulness(title_of_test, dataset)
    calc_answer_relevancy(title_of_test, dataset)
    calc_answer_similarity(title_of_test, dataset)
    calc_answer_correctness(title_of_test, dataset)

    # Write the description to a text file in the new directory
    description_file_path = directory_path / "description.txt"
    with open(description_file_path, "w") as file:
        file.write(description)
        logging.info(f"Description saved to {description_file_path}")


def generate_markdown_tables(base_path, output_file) -> None:
    """Updates or recreates a markdown table by adding new data from CSV files in subdirectories of the given base_path.
    Incorporates descriptions from 'description.txt' in each directory, if available, under a "Description" column.
    Ensures that only new subdirectories are processed, and adds a total score row for each test, highlighting the top 3 scores in green.
    If there are new tests, the whole table is recreated to ensure only the correct top 3 scores are highlighted.

    Args:
    ----
        base_path (str): Path to the base directory containing subdirectories with CSV files.
        output_file (str): Path to the output markdown file to create or update.

    """
    current_tests = set()
    results = {}
    categories = set()
    descriptions = {}
    total_scores = {}

    # Walk through all directories in the base path
    for root, _dirs, files in os.walk(base_path):
        test_name = os.path.basename(root).replace("_", " ").title()
        current_tests.add(test_name)

        csv_files = [file for file in files if file.endswith(".csv")]
        description_file = [file for file in files if file == "description.txt"]

        # Read description file
        description_content = "N/A"  # Default description
        if description_file:
            with open(os.path.join(root, description_file[0])) as df:
                description_content = df.read().strip()

        descriptions[test_name] = description_content

        if not csv_files:
            continue

        # Initialize test name in results
        results[test_name] = {}

        # Process each CSV file
        for csv_file in csv_files:
            csv_path = os.path.join(root, csv_file)
            try:
                df = pd.read_csv(csv_path)
                last_column = df.iloc[:, -1]
                last_column_numeric = pd.to_numeric(last_column, errors="coerce").fillna(0)
                category = " ".join(csv_file.replace(".csv", "").split("_")).title()
                categories.add(category)

                if category == "Harmlessness":
                    last_column_numeric = 1 - last_column_numeric

                average_score = last_column_numeric.mean()

                results[test_name][category] = average_score

            except Exception as e:
                print(f"Error processing {csv_path}: {e!s}")

        # Calculate total score for each test
        if test_name in results:
            scores = results[test_name].values()
            total_score = sum(scores) / len(scores) if scores else 0
            total_scores[test_name] = total_score

    # Read existing tests from the file
    existing_tests = set()
    try:
        with open(output_file) as file:
            for line in file:
                if "|" in line:
                    parts = line.split("|")
                    if len(parts) > 2:
                        test_name = parts[1].strip()
                        if test_name not in ("Test Name", "---"):
                            existing_tests.add(test_name)
    except FileNotFoundError:
        pass

    # Determine if there are new tests
    new_tests = current_tests != existing_tests

    # Identify top three scores
    top_scores = sorted(total_scores.values(), reverse=True)[:3]

    # Ensure the output directory exists
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Prepare to overwrite the file if new tests are detected or create new if not exists
    file_mode = "w" if new_tests else "a"
    sorted_categories = sorted(categories)

    with open(output_file, file_mode) as md_file:
        if new_tests or not existing_tests:  # Write headers if new tests or new file
            md_file.write("| Test Name | Description | " + " | ".join(sorted_categories) + " | Total Score |\n")
            md_file.write("| --- | --- |" + " --- |" * (len(categories) + 1) + "\n")

        # Write the data rows and total score
        for test_name, scores in results.items():
            row_scores = [scores.get(category, 0) for category in sorted_categories]
            total_score = total_scores[test_name]
            formatted_total_score = (
                f"<span style='color: green'>**{total_score:.4f}**</span>"
                if total_score in top_scores
                else f"**{total_score:.4f}**"
            )
            row = [f"{score:.4f}" for score in row_scores] + [formatted_total_score]
            md_file.write(f"| {test_name} | {descriptions[test_name]} | " + " | ".join(row) + " |\n")


def generate_dataset():
    import os

    def chunk_documents() -> list:
        directory_path = "./test_dataset"
        file_paths = [
            os.path.join(directory_path, file)
            for file in os.listdir(directory_path)
            if os.path.isfile(os.path.join(directory_path, file))
        ]

        all_chunks = []

        # Iterate over all files in the directory
        for file_path in file_paths:
            # Load the document
            docs = [doc for doc in PyMuPDFLoader(file_path=file_path, extract_images=False).load()]

            # Add metadata to each document
            for page, doc in enumerate(docs, 1):
                doc.metadata["page"] = page

            # Split documents into chunks
            chunks = RecursiveCharacterTextSplitter(
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
                length_function=len,
            ).split_documents([doc for doc in docs if doc.page_content])

            # Collect all chunks
            all_chunks.extend(chunks)

        return all_chunks

    from ragas.testset.generator import TestsetGenerator
    from ragas.testset.evolutions import simple, reasoning, multi_context

    generator = TestsetGenerator.from_langchain(
        generator_llm=settings.llm(LLMOptions.OPENAI),
        critic_llm=settings.llm(LLMOptions.OPENAI),
        embeddings=settings.embed_model,
    )
    testset = generator.generate_with_langchain_docs(
        chunk_documents(),
        test_size=50,
        distributions={simple: 0.5, reasoning: 0.25, multi_context: 0.25},
        raise_exceptions=False,
    )
    test_df = testset.to_pandas()
    test_df.to_csv("./datasets/dataset2.csv", index=False)


if __name__ == "__main__":
    # data = Dataset.from_dict(get_data_samples())
    # calc_faithfulness("testtitel", data)

    # calc_all(
    #     "PromptTest",
    #     "Old Type of prompt",
    # )
    # calc_prompt_compare(
    #     "New_prompt_test2",
    #     "NEW Type of prompt TOP K = 10",
    # )

    # generate_markdown_tables("results/prompt_tests/", "results/prompt_tests/results_table.md")
    generate_dataset()
