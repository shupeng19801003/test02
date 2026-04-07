from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.models import ChatRequest
from app.services.rag_chain import generate_rag_stream

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(req: ChatRequest):
    # If no doc_ids and no kb_id, search the entire global collection
    return EventSourceResponse(
        generate_rag_stream(
            question=req.question,
            kb_id=req.kb_id,
            top_k=req.top_k,
            doc_ids=req.doc_ids or None,
        ),
        media_type="text/event-stream",
    )
