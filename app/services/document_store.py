"""Unified document store for metadata and parsed text persistence.

Stores document metadata in a JSON file and parsed text sections
in individual JSON files, providing a single source of truth for
all modules (document management, audit, Q&A).
"""

import json
import os
import threading
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict

from app.config import settings

_STORE_DIR = os.path.join(settings.chroma_persist_dir, "..", "doc_store")
_META_FILE = os.path.join(_STORE_DIR, "metadata.json")
_SECTIONS_DIR = os.path.join(_STORE_DIR, "sections")
_lock = threading.Lock()


def _ensure_dirs():
    os.makedirs(_STORE_DIR, exist_ok=True)
    os.makedirs(_SECTIONS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class StoredDocument:
    id: str
    name: str
    size: int                          # bytes
    file_type: str                     # e.g. "pdf", "docx"
    chunk_count: int = 0
    uploaded_at: str = ""
    uploader: str = "system"
    folder: str = "/"                  # folder path, e.g. "/", "/reports/2024"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StoredDocument":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load_metadata() -> dict[str, dict]:
    _ensure_dirs()
    if not os.path.exists(_META_FILE):
        return {}
    with open(_META_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_metadata(data: dict[str, dict]):
    _ensure_dirs()
    with open(_META_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_document(doc: StoredDocument, sections: list[dict]):
    """Register a new document and persist its parsed text sections.

    Args:
        doc: StoredDocument metadata.
        sections: List of {"text": str, "metadata": dict} dicts
                  (serialised DocumentSection objects).
    """
    with _lock:
        meta = _load_metadata()
        meta[doc.id] = doc.to_dict()
        _save_metadata(meta)

    # Save sections to a separate file
    sec_path = os.path.join(_SECTIONS_DIR, f"{doc.id}.json")
    with open(sec_path, "w", encoding="utf-8") as f:
        json.dump(sections, f, ensure_ascii=False)


def get_document(doc_id: str) -> StoredDocument | None:
    """Return metadata for a single document, or None if not found."""
    meta = _load_metadata()
    entry = meta.get(doc_id)
    if entry is None:
        return None
    return StoredDocument.from_dict(entry)


def list_documents() -> list[StoredDocument]:
    """Return all stored documents sorted by upload time (newest first)."""
    meta = _load_metadata()
    docs = [StoredDocument.from_dict(v) for v in meta.values()]
    docs.sort(key=lambda d: d.uploaded_at, reverse=True)
    return docs


def delete_document(doc_id: str) -> bool:
    """Remove a document from the store.  Returns True if found & deleted."""
    with _lock:
        meta = _load_metadata()
        if doc_id not in meta:
            return False
        del meta[doc_id]
        _save_metadata(meta)

    sec_path = os.path.join(_SECTIONS_DIR, f"{doc_id}.json")
    if os.path.exists(sec_path):
        os.unlink(sec_path)
    return True


def get_sections(doc_id: str) -> list[dict] | None:
    """Load parsed text sections for a document.

    Returns list of {"text": str, "metadata": dict} or None.
    """
    sec_path = os.path.join(_SECTIONS_DIR, f"{doc_id}.json")
    if not os.path.exists(sec_path):
        return None
    with open(sec_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_sections_multi(doc_ids: list[str]) -> dict[str, list[dict]]:
    """Load sections for multiple documents.  Returns {doc_id: sections}."""
    result = {}
    for did in doc_ids:
        secs = get_sections(did)
        if secs is not None:
            result[did] = secs
    return result


# ---------------------------------------------------------------------------
# Folder management
# ---------------------------------------------------------------------------

_FOLDERS_FILE = os.path.join(_STORE_DIR, "folders.json")


def _load_folders() -> list[str]:
    """Load list of folder paths."""
    _ensure_dirs()
    if not os.path.exists(_FOLDERS_FILE):
        return ["/"]
    with open(_FOLDERS_FILE, "r", encoding="utf-8") as f:
        folders = json.load(f)
    if "/" not in folders:
        folders.insert(0, "/")
    return folders


def _save_folders(folders: list[str]):
    _ensure_dirs()
    with open(_FOLDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(folders, f, ensure_ascii=False, indent=2)


def list_folders() -> list[str]:
    """Return all folder paths sorted."""
    return sorted(_load_folders())


def create_folder(path: str) -> bool:
    """Create a new folder. Returns True if created, False if already exists."""
    # Normalize: ensure starts with / and no trailing /
    path = "/" + path.strip("/")
    if path != "/":
        path = path.rstrip("/")
    with _lock:
        folders = _load_folders()
        if path in folders:
            return False
        # Also ensure parent folders exist
        parts = path.strip("/").split("/")
        for i in range(1, len(parts) + 1):
            p = "/" + "/".join(parts[:i])
            if p not in folders:
                folders.append(p)
        _save_folders(folders)
    return True


def delete_folder(path: str) -> bool:
    """Delete a folder (and all sub-folders). Returns True if found & deleted.

    Note: Does NOT delete documents in the folder. Caller should move or
    delete them first.
    """
    path = "/" + path.strip("/")
    if path == "/":
        return False  # cannot delete root
    with _lock:
        folders = _load_folders()
        # Remove this folder and all sub-folders
        to_remove = [f for f in folders if f == path or f.startswith(path + "/")]
        if not to_remove:
            return False
        folders = [f for f in folders if f not in to_remove]
        _save_folders(folders)
    return True


def move_document(doc_id: str, new_folder: str) -> bool:
    """Move a document to a different folder."""
    new_folder = "/" + new_folder.strip("/")
    if new_folder != "/":
        new_folder = new_folder.rstrip("/")
    with _lock:
        meta = _load_metadata()
        if doc_id not in meta:
            return False
        meta[doc_id]["folder"] = new_folder
        _save_metadata(meta)
    return True


# Global ChromaDB collection name for the unified document library
GLOBAL_COLLECTION = "global_documents"
