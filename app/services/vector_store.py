"""Qdrant-backed semantic index for the product catalog.

Products are dual-written here from app.services.product_service whenever
they're created/updated/deleted in SQL, so retrieval is always grounded in
the real catalog. Embeddings are generated through Mesh (see mesh_client.py)
and always supplied explicitly — this module never asks Qdrant/any client
library to compute embeddings itself.

Backend selection: if QDRANT_URL is set, this talks to a real Qdrant server
(e.g. Qdrant Cloud's free tier). If it's unset, qdrant-client's embedded
"local mode" is used instead — a pure-Python implementation with no native
extension, so it needs no separate service for local development. (We
originally used Chroma here; it was swapped out after Chroma's native
hnswlib extension crashed with SIGILL on Render's free-tier CPU — a
virtualized-host CPU-feature-detection bug, not anything specific to our
usage. Qdrant's local mode being pure Python sidesteps that whole class of
bug, and pointing QDRANT_URL at a real cluster in production avoids it too.)
"""

import logging
from pathlib import Path
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config import settings
from app.services.mesh_client import get_embeddings_model

logger = logging.getLogger("smartreco.vector_store")

COLLECTION_NAME = "products"
BASE_DIR = Path(__file__).resolve().parent.parent.parent

_client: Optional[QdrantClient] = None
_collection_ready = False


def _local_path() -> str:
    path = settings.qdrant_local_path
    if path.startswith("./"):
        return str(BASE_DIR / path.removeprefix("./"))
    return path


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        if settings.qdrant_url:
            _client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
        else:
            _client = QdrantClient(path=_local_path())
    return _client


def _ensure_collection() -> QdrantClient:
    global _collection_ready
    client = _get_client()
    if not _collection_ready:
        if not client.collection_exists(COLLECTION_NAME):
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=qmodels.VectorParams(
                    size=settings.mesh_embedding_dim, distance=qmodels.Distance.COSINE
                ),
            )
        _collection_ready = True
    return client


def _document_text(title: str, description: str, category: str) -> str:
    return f"{title}\n\n{description}\n\nCategory: {category}"


def upsert_product(
    product_id: int, title: str, description: str, category: str, price: float, level: Optional[str]
) -> None:
    doc = _document_text(title, description, category)
    embedding = get_embeddings_model().embed_documents([doc])[0]
    client = _ensure_collection()
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            qmodels.PointStruct(
                id=product_id,
                vector=embedding,
                payload={
                    "title": title,
                    "category": category,
                    "price": float(price),
                    "level": level or "",
                },
            )
        ],
    )


def delete_product(product_id: int) -> None:
    try:
        client = _ensure_collection()
        client.delete(collection_name=COLLECTION_NAME, points_selector=qmodels.PointIdsList(points=[product_id]))
    except Exception:
        logger.warning("Failed to delete product %s from vector store", product_id, exc_info=True)


def query(query_text: str, top_k: int = 10, category: Optional[str] = None) -> list[dict[str, Any]]:
    client = _ensure_collection()
    try:
        count = client.count(collection_name=COLLECTION_NAME).count
    except Exception:
        count = 0
    if count == 0:
        return []

    embedding = get_embeddings_model().embed_query(query_text)
    query_filter = None
    if category:
        query_filter = qmodels.Filter(
            must=[qmodels.FieldCondition(key="category", match=qmodels.MatchValue(value=category))]
        )

    result = client.query_points(
        collection_name=COLLECTION_NAME,
        query=embedding,
        query_filter=query_filter,
        limit=min(top_k, count),
    )
    out = []
    for point in result.points:
        out.append(
            {
                "product_id": int(point.id),
                "metadata": point.payload,
                "score": point.score,  # cosine similarity: higher is closer, unlike Chroma's distance
            }
        )
    return out
