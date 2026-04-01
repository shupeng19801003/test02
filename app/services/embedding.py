from typing import Optional

from langchain_openai import OpenAIEmbeddings
from app.config import settings

_embeddings: Optional[OpenAIEmbeddings] = None


def get_embeddings() -> OpenAIEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model_name,
        )
    return _embeddings
