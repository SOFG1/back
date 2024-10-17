ARG PYTHON_VERSION_SHORT=3.12
ARG FINAL_VERSION="full"
ARG APP_VERSION=dev
ARG MODEL_FACEBOOK="facebook-contriever"
ARG MODEL_INTFLOAT="intfloat-multilingual-e5-large"

FROM python:${PYTHON_VERSION_SHORT}-slim AS base

ARG PYTHON_VERSION_SHORT=3.12
ENV PIP_DEFAULT_TIMEOUT=100 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/root/.local/bin:$PATH" \
    SITE_PACKAGES_PATH=/usr/local/lib/python${PYTHON_VERSION_SHORT}/site-packages/

ENV PYTHONPATH="$SITE_PACKAGES_PATH:${PYTHONPATH}"

# renovate: datasource=pypi depName=poetry versioning=semver
ENV POETRY_VERSION=1.8.3

RUN adduser --disabled-password worker

RUN apt-get update -y \
    && apt-get upgrade -y \
    && apt-get auto-remove \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder

RUN apt-get update -y \
    && apt-get install --no-install-recommends -y curl build-essential cargo \
    && curl -sSL https://install.python-poetry.org | python3 - --version ${POETRY_VERSION} \
    && poetry --version \
    && poetry config virtualenvs.create false \
    && apt-get auto-remove \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /usr/src/app

COPY pyproject.toml poetry.lock ./

FROM python:${PYTHON_VERSION_SHORT}-slim AS local-models

RUN pip install huggingface_hub[cli]

FROM local-models AS local-models-facebook-contriever

ARG MODEL_FACEBOOK

RUN --mount=type=cache,target="/models/${MODEL_FACEBOOK}/.cache" \
    huggingface-cli download facebook/contriever --local-dir "/models/${MODEL_FACEBOOK}"

FROM local-models AS local-models-intfloat-multilingual-e5-large

ARG MODEL_INTFLOAT

# TODO cache isn't working. Fix this.
RUN --mount=type=cache,target="/models/${MODEL_INTFLOAT}/.cache" \
    huggingface-cli download intfloat/multilingual-e5-large \
    --exclude "onnx/*" \
    modules.json \
    --local-dir "/models/${MODEL_INTFLOAT}"

FROM builder AS deps-full

RUN --mount=type=cache,target=/root/.cache \
    poetry install --no-interaction --no-ansi --no-root --only main --only local

FROM builder AS deps-remote

RUN --mount=type=cache,target=/root/.cache \
    poetry install --no-interaction --no-ansi --no-root --only main


FROM base AS wget

RUN apt-get update -y \
    && apt-get install --no-install-recommends -y wget \
    && apt-get auto-remove \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

FROM wget AS final-full

ARG MODEL_FACEBOOK
ARG MODEL_INTFLOAT

COPY --from=deps-full /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=deps-full "$SITE_PACKAGES_PATH" "$SITE_PACKAGES_PATH"
COPY --from=local-models-facebook-contriever "/models/${MODEL_FACEBOOK}" "/models/${MODEL_FACEBOOK}"
COPY --from=local-models-intfloat-multilingual-e5-large "/models/${MODEL_INTFLOAT}" "/models/${MODEL_INTFLOAT}"

FROM wget AS final-remote

COPY --from=deps-remote /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=deps-remote "$SITE_PACKAGES_PATH" "$SITE_PACKAGES_PATH"

FROM final-${FINAL_VERSION} AS final

RUN apt-get update -y \
    && apt-get install --no-install-recommends -y libgl1-mesa-glx libglib2.0-0 \
    && apt-get auto-remove \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ARG APP_VERSION
WORKDIR /usr/src/app
COPY --chown=worker:worker app /usr/src/app/app
COPY --chown=worker:worker migrations /usr/src/app/migrations
COPY --chown=worker:worker alembic.ini /usr/src/app/alembic.ini
COPY --chown=worker:worker main.py custom_prompts.py ./
COPY --chown=worker:worker .env.template .env
COPY --chown=worker:worker *.env .env
RUN chown worker:worker /usr/src/app
RUN mkdir -p /models
RUN chown -R worker:worker /models
USER worker
RUN mkdir -p data/uploads/ db/ /home/worker/.cache/torch/sentence_transformers

ENV PORT="8000"
EXPOSE $PORT
ENV APP_VERSION=${APP_VERSION}
ENV LANGFUSE_RELEASE=${APP_VERSION}
HEALTHCHECK CMD wget -q --no-cache --spider localhost:${PORT}/health || exit 1
CMD /usr/local/bin/uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers
