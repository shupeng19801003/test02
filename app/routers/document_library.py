"""Unified document library router.

Provides a single document pool used by both the Q&A and audit modules.
Documents are uploaded once, parsed, chunked, embedded, and persisted.
Supports hierarchical folder organisation.
"""

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from langchain_chroma import Chroma

from app.config import settings
from app.models import LibraryDocInfo
from app.utils.file_utils import is_supported_file, get_file_extension
from app.services.document_processor import process_file
from app.services.chunker import chunk_sections
from app.services.embedding import get_embeddings
from app.services.vector_store import get_chroma_client
from app.services.document_store import (
    StoredDocument, add_document, get_document, list_documents,
    delete_document, get_sections, GLOBAL_COLLECTION,
    list_folders, create_folder, delete_folder, move_document,
)

router = APIRouter(prefix="/api/documents", tags=["document-library"])


# ---------------------------------------------------------------------------
# Folder endpoints
# ---------------------------------------------------------------------------

@router.get("/folders")
async def get_folders():
    """Return all folder paths."""
    return list_folders()


@router.post("/folders")
async def add_folder(path: str = Form(...)):
    """Create a new folder (supports nested paths like /reports/2024)."""
    created = create_folder(path)
    if not created:
        raise HTTPException(status_code=409, detail="Folder already exists")
    return {"detail": "Folder created", "folders": list_folders()}


@router.delete("/folders")
async def remove_folder(path: str):
    """Delete a folder and all sub-folders."""
    deleted = delete_folder(path)
    if not deleted:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"detail": "Folder deleted", "folders": list_folders()}


@router.post("/{doc_id}/move")
async def move_doc(doc_id: str, folder: str = Form(...)):
    """Move a document to a different folder."""
    ok = move_document(doc_id, folder)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"detail": "Document moved"}


# ---------------------------------------------------------------------------
# Document CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=LibraryDocInfo)
async def upload_document(
    file: UploadFile = File(...),
    folder: str = Form("/"),
):
    """Upload a document to the unified library."""
    if not file.filename or not is_supported_file(file.filename):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    doc_id = uuid.uuid4().hex[:12]
    file_path = os.path.join(settings.upload_dir, f"{doc_id}_{file.filename}")

    # Normalize folder
    folder = "/" + folder.strip("/")
    if folder != "/":
        folder = folder.rstrip("/")

    try:
        content = await file.read()
        if len(content) > settings.max_file_size_mb * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large")

        with open(file_path, "wb") as f:
            f.write(content)

        # Parse document
        sections = process_file(file_path, file.filename)
        if not sections:
            raise HTTPException(status_code=400, detail="No text content extracted")

        # Chunk for embedding
        chunks = chunk_sections(sections)

        # Prepare data for ChromaDB
        texts = [c.text for c in chunks]
        now_iso = datetime.now(timezone.utc).isoformat()
        metadatas = []
        ids = []
        for i, chunk in enumerate(chunks):
            meta = {
                **chunk.metadata,
                "doc_id": doc_id,
                "doc_name": file.filename,
                "uploaded_at": now_iso,
            }
            metadatas.append(meta)
            ids.append(f"{doc_id}_chunk_{i}")

        # Store embeddings in global collection
        vectorstore = Chroma(
            client=get_chroma_client(),
            collection_name=GLOBAL_COLLECTION,
            embedding_function=get_embeddings(),
        )
        vectorstore.add_texts(texts=texts, metadatas=metadatas, ids=ids)

        # Persist metadata + raw sections to document store
        ext = get_file_extension(file.filename).lstrip(".")
        stored = StoredDocument(
            id=doc_id,
            name=file.filename,
            size=len(content),
            file_type=ext,
            chunk_count=len(chunks),
            uploaded_at=now_iso,
            folder=folder,
        )
        section_dicts = [{"text": s.text, "metadata": s.metadata} for s in sections]
        add_document(stored, section_dicts)

        # Ensure folder exists
        create_folder(folder)

        return LibraryDocInfo(**stored.to_dict())

    finally:
        if os.path.exists(file_path):
            os.unlink(file_path)


@router.get("", response_model=list[LibraryDocInfo])
async def list_all_documents():
    """List all documents in the unified library."""
    docs = list_documents()
    return [LibraryDocInfo(**d.to_dict()) for d in docs]


@router.get("/{doc_id}", response_model=LibraryDocInfo)
async def get_document_info(doc_id: str):
    """Get metadata for a single document."""
    doc = get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return LibraryDocInfo(**doc.to_dict())


@router.get("/{doc_id}/content")
async def get_document_content(doc_id: str):
    """Return parsed text content for in-browser preview."""
    doc = get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    sections = get_sections(doc_id)
    if sections is None:
        raise HTTPException(status_code=404, detail="Document content not found")

    return {
        "doc_id": doc_id,
        "filename": doc.name,
        "sections": sections,
    }


@router.delete("/{doc_id}")
async def remove_document(doc_id: str):
    """Delete a document from the library and its embeddings."""
    doc = get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove chunks from global ChromaDB collection
    try:
        client = get_chroma_client()
        col = client.get_or_create_collection(name=GLOBAL_COLLECTION)
        # Find all chunk IDs for this document
        all_data = col.get(include=["metadatas"])
        ids_to_delete = []
        for chunk_id, meta in zip(all_data["ids"], all_data.get("metadatas") or []):
            if meta and meta.get("doc_id") == doc_id:
                ids_to_delete.append(chunk_id)
        if ids_to_delete:
            col.delete(ids=ids_to_delete)
    except Exception:
        pass  # best-effort cleanup

    # Remove from document store
    delete_document(doc_id)
    return {"detail": "Document deleted"}
