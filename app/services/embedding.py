"""Embedding service supporting multiple providers.

Providers:
- "api": OpenAI-compatible API (e.g., Volcano Engine ARK, LM Studio)
- "local": HuggingFace sentence-transformers (requires sentence-transformers)
"""

from typing import Optional
from langchain_core.embeddings import Embeddings
from app.config import settings

_embeddings: Optional[Embeddings] = None


def get_embeddings() -> Embeddings:
    """Get embedding model instance."""
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    provider = settings.embedding_provider

    if provider == "api":
        from langchain_openai import OpenAIEmbeddings
        _embeddings = OpenAIEmbeddings(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model_name,
        )
    else:
        # Local: use HuggingFace sentence-transformers
        from langchain_huggingface import HuggingFaceEmbeddings
        _embeddings = HuggingFaceEmbeddings(
            model_name=settings.embedding_model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    return _embeddings
