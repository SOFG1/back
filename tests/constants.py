import json
from datetime import UTC, datetime
from types import SimpleNamespace

DEFAULT_CREATED_MODIFIED_TIME = datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC)
NEW_INDEX_TEST_NAMESPACE = "default_index_openai_text_embedding_3_small"
MOCK_LIST_OLD_VALUES = {
    "index_1": SimpleNamespace(
        name="Index 1",
        description="Test description",
        generative_config={},
        properties=[
            SimpleNamespace(
                name="prop_1",
                description="Property 1",
                data_type="string",
                index_filterable=True,
                index_range_filters=False,
                index_searchable=True,
                nested_properties=[],
                tokenization="word",
                vectorizer_config={},
                vectorizer="vectorizer_1",
            )
        ],
        references=[],
        reranker_config={},
        vectorizer_config={},
        vectorizer="vectorizer_1",
        vector_config={},
    ),
    NEW_INDEX_TEST_NAMESPACE: SimpleNamespace(
        name=NEW_INDEX_TEST_NAMESPACE,
        description="Another test description",
        generative_config={},
        properties=[
            SimpleNamespace(
                name="prop_2",
                description="Property 2",
                data_type="int",
                index_filterable=True,
                index_range_filters=False,
                index_searchable=True,
                nested_properties=[],
                tokenization="word",
                vectorizer_config={},
                vectorizer="vectorizer_2",
            )
        ],
        references=[],
        reranker_config={},
        vectorizer_config={},
        vectorizer="vectorizer_2",
        vector_config={},
    ),
}
LIST_OLD_COLLECTED_RESPONSE = {"old_indexes": ["Index 1"]}
CURRENT_INDEX_INVALID_STR_RESPONSE = ""

CURRENTS_INDEX_VALID_STR_RESPONSE = "config=" + json.dumps(
    {
        "name": NEW_INDEX_TEST_NAMESPACE,
        "description": None,
        "generative_config": None,
        "inverted_index_config": {
            "bm25": {"b": 0.75, "k1": 1.2},
            "cleanup_interval_seconds": 60,
            "index_null_state": False,
            "index_property_length": False,
            "index_timestamps": False,
            "stopwords": {"preset": "en", "additions": None, "removals": None},
        },
        "multi_tenancy_config": {"enabled": False, "auto_tenant_creation": False, "auto_tenant_activation": False},
        "properties": [
            {
                "name": "text",
                "description": None,
                "data_type": "text",
                "index_filterable": True,
                "index_range_filters": False,
                "index_searchable": True,
                "nested_properties": None,
                "tokenization": "word",
                "vectorizer_config": None,
                "vectorizer": "none",
            }
        ],
        "references": [],
        "replication_config": {"factor": 1, "async_enabled": False},
        "reranker_config": None,
        "sharding_config": {
            "virtual_per_physical": 128,
            "desired_count": 1,
            "actual_count": 1,
            "desired_virtual_count": 128,
            "actual_virtual_count": 128,
            "key": "_id",
            "strategy": "hash",
            "function": "murmur3",
        },
        "vector_index_config": {
            "quantizer": None,
            "cleanup_interval_seconds": 300,
            "distance_metric": "cosine",
            "dynamic_ef_min": 100,
            "dynamic_ef_max": 500,
            "dynamic_ef_factor": 8,
            "ef": -1,
            "ef_construction": 128,
            "flat_search_cutoff": 40000,
            "max_connections": 32,
            "skip": False,
            "vector_cache_max_objects": 1000000000000,
        },
        "vector_index_type": "hnsw",
        "vectorizer_config": None,
        "vectorizer": "none",
        "vector_config": None,
    }
)

CURRENT_INDEX_EXPECTED_RESPONSE = {"current_index": NEW_INDEX_TEST_NAMESPACE}
