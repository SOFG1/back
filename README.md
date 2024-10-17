# TextSenseAI Backend

## Contributing

Take a look at the [Issue Board on JIRA](https://skillbyte.atlassian.net/jira/software/projects/TEX/boards/50).

## Setup:
* install [poetry](https://python-poetry.org/) and then run
```shell
poetry install
```
* install [ollama](https://github.com/ollama/ollama)
```shell
curl -fsSL https://ollama.com/install.sh | sh
```

### External providers

Create a new `.env` file:

```shell
cp .env.template .env
```

And fill in the values that are only placeholders. Ask the other team members for the secret keys.

### Chat LLM
After installing run this in the terminal:
```shell
MODEL=llama3
ollama pull $MODEL
```
where the current MODEL can be found in `.env`.

Ollama has a ton of supported models, see [here](https://github.com/ollama/ollama?tab=readme-ov-file#model-library)

### Embeddings LLM
This will automatically be downloaded when starting the backend. The current model can be found on Huggingface: [facebook/contriever](https://huggingface.co/facebook/contriever)

### Vector DB

We currently use Weaviate as a VectorDB. It is persisted as a docker volume.

```shell
docker compose up -d weaviate
```

To request weaviate:

```shell
docker-compose exec weaviate wget -O- --header "Authorization: Bearer skillbyte" localhost:8080/v1/objects
```

### Start backend

For development purposes, run the backend using the following command:

```shell
poetry run python main.py
```

You can override which device each model runs on:

```shell
LLM_DEVICE=cuda EMBEDDING_DEVICE=cpu python main.py
```

Alternatively, run the backend using docker-compose:

```shell
docker compose up -d backend
```

Or all services (Weaviate and the backend), with:

```shell
docker compose up -d
```

You can also start all backend services **and** the frontend with one command. This assumes that the frontend repo is
checked out under `../tsai-frontend`:

```shell
docker compose -f docker-compose-with-frontend.yaml up -d
```

In order for the backend service to be able to communicate with Ollama, you need to either run Ollama also in the same Docker network (no GPU acceleration available on Mac), or configure your Ollama to bind to host `0.0.0.0` instead of `127.0.0.1`, as described [here](https://github.com/ollama/ollama/blob/main/docs/faq.md#how-do-i-configure-ollama-server):

#### Setting environment variables on Mac

If Ollama is run as a macOS application, environment variables should be set using `launchctl`:

1. For each environment variable, call `launchctl setenv`.

    ```bash
    launchctl setenv OLLAMA_HOST "0.0.0.0"
    ```

2. Restart Ollama application.

#### Setting environment variables on Linux

If Ollama is run as a systemd service, environment variables should be set using `systemctl`:

1. Edit the systemd service by calling `systemctl edit ollama.service`. This will open an editor.

2. For each environment variable, add a line `Environment` under section `[Service]`:

    ```ini
    [Service]
    Environment="OLLAMA_HOST=0.0.0.0"
    ```

3. Save and exit.

4. Reload `systemd` and restart Ollama:

   ```bash
   systemctl daemon-reload
   systemctl restart ollama
   ```

#### Setting environment variables on Windows

On Windows, Ollama inherits your user and system environment variables.

1. First Quit Ollama by clicking on it in the task bar.

2. Start the Settings (Windows 11) or Control Panel (Windows 10) application and search for _environment variables_.

3. Click on _Edit environment variables for your account_.

4. Edit or create a new variable for your user account for `OLLAMA_HOST`, `OLLAMA_MODELS`, etc.

5. Click OK/Apply to save.

6. Start the Ollama application from the Windows Start menu.

### LLM Observability

We use [Langfuse](https://langfuse.com) to monitor our LLM (usage, cost and user feedback).

Visit [http://localhost:3001](http://localhost:3001) for the UI. When running locally, the credentials are:

- Email: `admin@skillbyte.de`
- Password: `skillbyte`

### Environment Variable Options:

#### EMBEDDING_LLM=openchat
for Extractors by far qwen:14b or higher

Best 7B yet: zephyr > openchat

#### CHAT_LLM=openchat
zephyr, openchat -> both fine

starling-lm -> was fine but is hallucinating since update

Other options: see [here](https://ollama.com/library)

#### LLM_TEMPERATURE
Anything between 0 and 1 can be tested.

Closer to 1 -> LLM answers more creative

Closer to 0 -> LLM answers more contextual

#### EMBEDDING_MODEL
Currently: facebook/contriever (Max Sequence length: Unknown, but really high over 2048 still working)

Other options:

intfloat/multilingual-e5-large (Max sequence length: 512) -> CHUNK_SIZE needs to be smaller than the current 512

sentence-transformers/all-mpnet-base-v2 ( Max sequence length: unknown, 300 working fine)

BAAI/bge-m3 (Max sequence length: 8192)

And many more, see benchmark graph:

![See](https://huggingface.co/blog/assets/110_mteb/benchmark.png)

#### CHUNK_SIZE (_**CURRENTLY NOT IN USE**_)

Sets the max size of a text chunk from a document

Currently: 512

testing can be done with any number, respecting the max sequence length of the currently used embedding model

#### CHUNK_OVERLAP (_**CURRENTLY NOT IN USE**_)
Sets how much of the previous chunk is allowed to reoccur in the next chunk

Experimenting can be done with any value as long as it is lower than the CHUNK_SIZE

#### CHAT_MODE
Sets the chatmode of the chatengine

currently supports `context` and `condense_plus_context` in the german language

Other modes are possible to implement, see [here](#chat-engine-modes)

### Prompts (_**Moved to backend/custom_prompts.py**_)
All prompts can be experimented with but should each follow the same concept


#### SYSTEM_PROMPT
Should be a simple instruction to the system what it is and what it does

#### CONTEXT_PROMPT_TEMPLATE
Gives the LLM the context information for the asked question and a precise instruction on what to do with the information and how to react if it cant answer the question with the given context

#### CONTEXT_PROMPT
Same as CONTEXT_PROMPT_TEMPLATE just with the {query_str} for the text_qa_template within engine.init

#### CONDENSE_PROMPT_TEMPLATE
For Chatmode condense_plus_context

Condenses the previous conversation and rewrites the new question based on previous messages

#### DEFAULT_QA_EXTRACTOR_TEMPLATE_DE
Forms questions based on the context of each chunk
#### QUESTION_NUM
Sets how many questions should be created per chunk in a document


### Chat Engine Modes

    SIMPLE = "simple"
    """Corresponds to `SimpleChatEngine`.

    Chat with LLM, without making use of a knowledge base.
    """

    CONDENSE_QUESTION = "condense_question"
    """Corresponds to `CondenseQuestionChatEngine`.

    First generate a standalone question from conversation context and last message,
    then query the query engine for a response.
    """

    CONTEXT = "context"
    """Corresponds to `ContextChatEngine`.

    First retrieve text from the index using the user's message, then use the context
    in the system prompt to generate a response.
    """

    CONDENSE_PLUS_CONTEXT = "condense_plus_context"
    """Corresponds to `CondensePlusContextChatEngine`.

    First condense a conversation and latest user message to a standalone question.
    Then build a context for the standalone question from a retriever,
    Then pass the context along with prompt and user message to LLM to generate a response.
    """

    REACT = "react"
    """Corresponds to `ReActAgent`.

    Use a ReAct agent loop with query engine tools.
    """

    OPENAI = "openai"
    """Corresponds to `OpenAIAgent`.

    Use an OpenAI function calling agent loop.

    NOTE: only works with OpenAI models that support function calling API.
    """

    BEST = "best"
    """Select the best chat engine based on the current LLM.

    Corresponds to `OpenAIAgent` if using an OpenAI model that supports
    function calling API, otherwise, corresponds to `ReActAgent`.
    """


## Metric explanation:
* [calc_faithfulness](https://docs.ragas.io/en/latest/concepts/metrics/faithfulness.html)
* [calc_answer_relevancy](https://docs.ragas.io/en/latest/concepts/metrics/answer_relevance.html)
* [calc_context_recall](https://docs.ragas.io/en/latest/concepts/metrics/context_recall.html)
* [calc_context_precision](https://docs.ragas.io/en/latest/concepts/metrics/context_precision.html)
* [calc_context_relevancy](https://docs.ragas.io/en/latest/concepts/metrics/context_relevancy.html)
* [calc_context_entity_recall](https://docs.ragas.io/en/latest/concepts/metrics/context_entities_recall.html)
* [calc_answer_similarity](https://docs.ragas.io/en/latest/concepts/metrics/semantic_similarity.html)
* [calc_answer_correctness](https://docs.ragas.io/en/latest/concepts/metrics/answer_correctness.html)
* [calc_harmfulness](https://docs.ragas.io/en/latest/concepts/metrics/critique.html)
