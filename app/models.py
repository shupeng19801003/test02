from datetime import datetime
from pydantic import BaseModel


# --- Knowledge Base ---

class KBCreate(BaseModel):
    name: str
    description: str = ""


class KBInfo(BaseModel):
    id: str
    name: str
    description: str
    doc_count: int = 0
    created_at: str = ""


# --- Document ---

class DocInfo(BaseModel):
    id: str
    name: str
    chunk_count: int = 0
    uploaded_at: str = ""


# --- Chat ---

class ChatRequest(BaseModel):
    question: str
    kb_id: str
    top_k: int = 4


# --- Audit ---

class AuditRequest(BaseModel):
    categories: list[str] = []  # empty = all categories


class AuditHitInfo(BaseModel):
    category: str
    category_label: str
    keyword: str
    description: str
    location: str
    context: str
    severity: str
    suggestion: str


class AuditResponse(BaseModel):
    filename: str
    total_hits: int
    risk_level: str
    hits: list[AuditHitInfo]
    category_summary: dict[str, int]
