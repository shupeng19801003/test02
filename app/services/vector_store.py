from typing import Optional

import chromadb
from app.config import settings

# Singleton ChromaDB client
_client: Optional[chromadb.PersistentClient] = None


def get_chroma_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    return _client


def get_collection_name(kb_id: str) -> str:
    return f"kb_{kb_id}"


def create_collection(kb_id: str, metadata: dict) -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=get_collection_name(kb_id),
        metadata=metadata,
    )


def get_collection(kb_id: str) -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_collection(name=get_collection_name(kb_id))


def delete_collection(kb_id: str):
    client = get_chroma_client()
    client.delete_collection(name=get_collection_name(kb_id))


def list_collections() -> list:
    client = get_chroma_client()
    return client.list_collections()
