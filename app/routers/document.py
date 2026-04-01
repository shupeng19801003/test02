import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File
from langchain_chroma import Chroma

from app.config import settings
from app.models import DocInfo
from app.utils.file_utils import is_supported_file
from app.services.document_processor import process_file
from app.services.chunker import chunk_sections
from app.services.embedding import get_embeddings
from app.services.vector_store import get_collection_name, get_chroma_client

router = APIRouter(prefix="/api/knowledge-bases/{kb_id}/documents", tags=["documents"])


@router.post("", response_model=DocInfo)
async def upload_document(kb_id: str, file: UploadFile = File(...)):
    if not file.filename or not is_supported_file(file.filename):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    # Verify KB exists
    try:
        client = get_chroma_client()
        client.get_collection(name=get_collection_name(kb_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Save uploaded file temporarily
    doc_id = uuid.uuid4().hex[:12]
    file_path = os.path.join(settings.upload_dir, f"{doc_id}_{file.filename}")
    try:
        content = await file.read()
        if len(content) > settings.max_file_size_mb * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large")

        with open(file_path, "wb") as f:
            f.write(content)

        # Process document: parse -> chunk -> embed -> store
        sections = process_file(file_path, file.filename)
        if not sections:
            raise HTTPException(status_code=400, detail="No text content extracted from file")

        chunks = chunk_sections(sections)

        # Prepare data for ChromaDB
        texts = [c.text for c in chunks]
        metadatas = []
        ids = []
        for i, chunk in enumerate(chunks):
            meta = {
                **chunk.metadata,
                "doc_id": doc_id,
                "doc_name": file.filename,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
            metadatas.append(meta)
            ids.append(f"{doc_id}_chunk_{i}")

        # Store embeddings in ChromaDB via LangChain
        vectorstore = Chroma(
            client=get_chroma_client(),
            collection_name=get_collection_name(kb_id),
            embedding_function=get_embeddings(),
        )
        vectorstore.add_texts(texts=texts, metadatas=metadatas, ids=ids)

        return DocInfo(
            id=doc_id,
            name=file.filename,
            chunk_count=len(chunks),
            uploaded_at=metadatas[0]["uploaded_at"],
        )
    finally:
        # Clean up temp file
        if os.path.exists(file_path):
            os.unlink(file_path)


@router.get("", response_model=list[DocInfo])
async def list_documents(kb_id: str):
    try:
        client = get_chroma_client()
        col = client.get_collection(name=get_collection_name(kb_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    all_data = col.get(include=["metadatas"])
    docs = {}
    for meta in (all_data.get("metadatas") or []):
        if not meta or "doc_id" not in meta:
            continue
        did = meta["doc_id"]
        if did not in docs:
            docs[did] = {
                "id": did,
                "name": meta.get("doc_name", ""),
                "chunk_count": 0,
                "uploaded_at": meta.get("uploaded_at", ""),
            }
        docs[did]["chunk_count"] += 1

    return [DocInfo(**d) for d in docs.values()]


@router.delete("/{doc_id}")
async def delete_document(kb_id: str, doc_id: str):
    try:
        client = get_chroma_client()
        col = client.get_collection(name=get_collection_name(kb_id))
    except Exception:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Find all chunk IDs for this document
    all_data = col.get(include=["metadatas"])
    ids_to_delete = []
    for chunk_id, meta in zip(all_data["ids"], all_data.get("metadatas") or []):
        if meta and meta.get("doc_id") == doc_id:
            ids_to_delete.append(chunk_id)

    if not ids_to_delete:
        raise HTTPException(status_code=404, detail="Document not found")

    col.delete(ids=ids_to_delete)
    return {"detail": f"Document deleted, {len(ids_to_delete)} chunks removed"}
