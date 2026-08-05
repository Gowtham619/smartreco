"""Chroma-backed semantic index for the product catalog.

Products are dual-written here from app.services.product_service whenever
they're created/updated/deleted in SQL, so retrieval is always grounded in
the real catalog. Embeddings are generated through Mesh (see mesh_client.py),
never through Chroma's own default embedding function.
"""

import logging
from pathlib import Path
from typing import Any, Optional

import chromadb

from app.config import settings
from app.services.mesh_client import get_embeddings_model

logger = logging.getLogger("smartreco.vector_store")

_client: chromadb.ClientAPI | None = None
_collection = None

COLLECTION_NAME = "products"
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class _UnusedEmbeddingFunction:
    """Every call site here supplies precomputed Mesh embeddings explicitly, so
    this should never actually run. It exists only to stop Chroma from falling
    back to its bundled ONNX MiniLM default, which pulls in onnxruntime — that
    native dependency has been observed to crash with SIGILL on some cloud
    hosts' CPUs (e.g. Render) the moment a collection touches it, even though
    we never call it."""

    def __call__(self, input):  # noqa: A002 - name required by Chroma's protocol
        raise RuntimeError(
            "SmartReco always supplies embeddings explicitly; Chroma's default "
            "embedding function should never be invoked."
        )


def _persist_dir() -> str:
    persist_dir = settings.chroma_persist_dir
    if persist_dir.startswith("./"):
        return str(BASE_DIR / persist_dir.removeprefix("./"))
    return persist_dir


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=_persist_dir())
        _collection = _client.get_or_create_collection(
            COLLECTION_NAME, embedding_function=_UnusedEmbeddingFunction()
        )
    return _collection


def _document_text(title: str, description: str, category: str) -> str:
    return f"{title}\n\n{description}\n\nCategory: {category}"


def upsert_product(
    product_id: int, title: str, description: str, category: str, price: float, level: Optional[str]
) -> None:
    doc = _document_text(title, description, category)
    embedding = get_embeddings_model().embed_documents([doc])[0]
    _get_collection().upsert(
        ids=[str(product_id)],
        embeddings=[embedding],
        documents=[doc],
        metadatas=[
            {
                "title": title,
                "category": category,
                "price": float(price),
                "level": level or "",
            }
        ],
    )


def delete_product(product_id: int) -> None:
    try:
        _get_collection().delete(ids=[str(product_id)])
    except Exception:
        logger.warning("Failed to delete product %s from vector store", product_id, exc_info=True)


def query(query_text: str, top_k: int = 10, category: Optional[str] = None) -> list[dict[str, Any]]:
    embedding = get_embeddings_model().embed_query(query_text)
    where = {"category": category} if category else None
    collection = _get_collection()
    count = collection.count()
    if count == 0:
        return []
    result = collection.query(
        query_embeddings=[embedding],
        n_results=min(top_k, count),
        where=where,
    )
    if not result["ids"] or not result["ids"][0]:
        return []
    out = []
    for i, doc_id in enumerate(result["ids"][0]):
        out.append(
            {
                "product_id": int(doc_id),
                "metadata": result["metadatas"][0][i],
                "distance": result["distances"][0][i] if result.get("distances") else None,
            }
        )
    return out
