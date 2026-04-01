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
