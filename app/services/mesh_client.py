"""Shared clients for talking to the Mesh API (mandatory LLM/embedding gateway).

Everything here points at MESH_BASE_URL with MESH_API_KEY — no direct calls to
OpenAI or any other provider. Using the langchain_openai wrappers (rather than
the raw openai SDK) means LangGraph node calls get automatic LangSmith tracing
for free when LANGCHAIN_TRACING_V2 is set, with zero extra instrumentation code.
"""

from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import OpenAI

from app.config import settings


@lru_cache
def get_raw_client() -> OpenAI:
    return OpenAI(base_url=settings.mesh_base_url, api_key=settings.mesh_api_key)


@lru_cache
def get_chat_model() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.mesh_base_url,
        api_key=settings.mesh_api_key,
        model=settings.mesh_chat_model,
        temperature=0.7,
    )


@lru_cache
def get_embeddings_model() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        base_url=settings.mesh_base_url,
        api_key=settings.mesh_api_key,
        model=settings.mesh_embedding_model,
    )
