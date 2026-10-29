import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.config import Config
from dotenv import load_dotenv

DOCUMENTS_PATH = Path(__file__).parent / "data" / "documents.json"
DATE_FIELDS = ["earliest_start_date", "latest_end_date", "applications_close_date"]
EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
DIMENSION = 1024
BATCH_SIZE = 500
MAX_NATIONALITIES = 60
NON_FILTERABLE_KEYS = [
    "embedding_text",
    "title",
    "location",
    "organisation",
    "host_lc",
    "lat",
    "lng",
    "text_hash",
]

load_dotenv()
REGION = os.environ.get("AWS_REGION", "eu-west-1")
BUCKET_NAME = os.environ.get("VECTOR_BUCKET", "yop-test")
INDEX_NAME = os.environ.get("VECTOR_INDEX", "opportunities")

RETRY_CONFIG = Config(retries={"max_attempts": 10, "mode": "adaptive"})


@lru_cache(maxsize=1)
def s3vectors():
    return boto3.client("s3vectors", region_name=REGION, config=RETRY_CONFIG)


@lru_cache(maxsize=1)
def bedrock():
    return boto3.client("bedrock-runtime", region_name=REGION, config=RETRY_CONFIG)


def embed(text):
    response = bedrock().invoke_model(
        modelId=EMBEDDING_MODEL,
        body=json.dumps(
            {"inputText": text, "dimensions": DIMENSION, "normalize": True}
        ),
    )
    return json.loads(response["body"].read())["embedding"]


def date_to_int(value):
    return int(value.replace("-", "")) if value else None


def to_metadata(doc):
    metadata = dict(doc["metadata"])
    if len(metadata["nationalities"]) > MAX_NATIONALITIES:
        metadata["nationalities"] = []
    metadata["open_to_all_nationalities"] = not metadata["nationalities"]
    for field in DATE_FIELDS:
        metadata[field] = date_to_int(metadata[field])

    metadata["embedding_text"] = doc["embedding_text"]
    metadata["text_hash"] = hashlib.sha1(doc["embedding_text"].encode()).hexdigest()[
        :16
    ]
    return {k: v for k, v in metadata.items() if v is not None and v != []}


def recreate_index():
    client = s3vectors()
    # drop and recreate so opportunities that closed since the last run are removed
    try:
        client.delete_index(vectorBucketName=BUCKET_NAME, indexName=INDEX_NAME)
    except client.exceptions.NotFoundException:
        pass

    client.create_index(
        vectorBucketName=BUCKET_NAME,
        indexName=INDEX_NAME,
        dataType="float32",
        dimension=DIMENSION,
        distanceMetric="cosine",
        metadataConfiguration={"nonFilterableMetadataKeys": NON_FILTERABLE_KEYS},
    )


def upload_documents():
    documents = json.loads(DOCUMENTS_PATH.read_text())

    # embed each distinct text once, copies of the same project reuse it
    texts = sorted({doc["embedding_text"] for doc in documents})
    print(f"Embedding {len(texts)} distinct texts with {EMBEDDING_MODEL}...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        embeddings = dict(zip(texts, pool.map(embed, texts)))

    vectors = [
        {
            "key": doc["id"],
            "data": {"float32": embeddings[doc["embedding_text"]]},
            "metadata": to_metadata(doc),
        }
        for doc in documents
    ]

    recreate_index()
    for start in range(0, len(vectors), BATCH_SIZE):
        s3vectors().put_vectors(
            vectorBucketName=BUCKET_NAME,
            indexName=INDEX_NAME,
            vectors=vectors[start : start + BATCH_SIZE],
        )
        print(f"uploaded {min(start + BATCH_SIZE, len(vectors))}/{len(vectors)}")

    print(f"Uploaded {len(vectors)} vectors to {BUCKET_NAME}/{INDEX_NAME}")


def search_opportunities(profile_text, filter=None, top_k=10):
    """Return the best matching opportunities, one per distinct description."""
    query = {
        "vectorBucketName": BUCKET_NAME,
        "indexName": INDEX_NAME,
        "queryVector": {"float32": embed(profile_text)},
        # fetch extra so duplicates of the same project can be collapsed
        "topK": top_k * 4,
        "returnMetadata": True,
        "returnDistance": True,
    }
    if filter:
        query["filter"] = filter

    matches = {}
    for vector in s3vectors().query_vectors(**query)["vectors"]:
        metadata = vector.get("metadata") or {}
        key = metadata.get("text_hash", vector["key"])
        if key in matches:
            matches[key]["duplicate_ids"].append(vector["key"])
            continue
        matches[key] = {
            **metadata,
            "id": vector["key"],
            # cosine distance -> similarity, higher is better
            "score": 1 - vector["distance"],
            "duplicate_ids": [],
        }
        if len(matches) == top_k:
            break
    return list(matches.values())
