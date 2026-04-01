import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from app.models import KBCreate, KBInfo
from app.services.vector_store import (
    create_collection,
    get_collection,
    delete_collection,
    list_collections,
)

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


@router.post("", response_model=KBInfo)
async def create_knowledge_base(req: KBCreate):
    kb_id = uuid.uuid4().hex[:12]
    metadata = {
        "kb_id": kb_id,
        "name": req.name,
        "description": req.description,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    create_collection(kb_id, metadata)
    return KBInfo(
        id=kb_id,
        name=req.name,
        description=req.description,
        doc_count=0,
        created_at=metadata["created_at"],
    )


@router.get("", response_model=list[KBInfo])
async def list_knowledge_bases():
    collections = list_collections()
    result = []
    for name in collections:
        col_name = name if isinstance(name, str) else name.name if hasattr(name, "name") else str(name)
        if not col_name.startswith("kb_"):
            continue
        try:
            from app.services.vector_store import get_chroma_client
            col = get_chroma_client().get_collection(name=col_name)
            meta = col.metadata or {}
            # Count distinct doc_ids
            all_meta = col.get(include=["metadatas"])
            doc_ids = set()
            for m in (all_meta.get("metadatas") or []):
                if m and "doc_id" in m:
                    doc_ids.add(m["doc_id"])
            result.append(KBInfo(
                id=meta.get("kb_id", col_name.replace("kb_", "")),
                name=meta.get("name", col_name),
                description=meta.get("description", ""),
                doc_count=len(doc_ids),
                created_at=meta.get("created_at", ""),
            ))
        except Exception:
            continue
    return result


@router.get("/{kb_id}", response_model=KBInfo)
async def get_knowledge_base(kb_id: str):
    try:
        col = get_collection(kb_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    meta = col.metadata or {}
    all_meta = col.get(include=["metadatas"])
    doc_ids = set()
    for m in (all_meta.get("metadatas") or []):
        if m and "doc_id" in m:
            doc_ids.add(m["doc_id"])
    return KBInfo(
        id=kb_id,
        name=meta.get("name", ""),
        description=meta.get("description", ""),
        doc_count=len(doc_ids),
        created_at=meta.get("created_at", ""),
    )


@router.delete("/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    try:
        delete_collection(kb_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return {"detail": "Knowledge base deleted"}
