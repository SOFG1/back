from math import inf

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_fastapi_instrumentator import Instrumentator, metrics


def add_metrics(app: FastAPI) -> None:
    # logarithmically spaced buckets
    buckets = (
        0.001,
        0.003,
        0.008,
        0.022,
        0.06,
        0.167,
        0.464,
        1.292,
        3.594,
        10.0,
        inf,
    )
    instrumentator = (
        Instrumentator(
            should_group_status_codes=True,
            should_group_untemplated=True,
            should_instrument_requests_inprogress=True,
            excluded_handlers=["/metrics", "/api/docs", "/redocs", "/health", "/api/version", "/api/openapi.json"],
            inprogress_labels=True,
        )
        .add(metrics.request_size())
        .add(metrics.response_size())
        .add(metrics.latency(buckets=buckets))
        .add(metrics.requests())
    )
    instrumentator.instrument(app).expose(app, response_class=PlainTextResponse)
