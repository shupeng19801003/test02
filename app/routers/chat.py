from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.models import ChatRequest
from app.services.rag_chain import generate_rag_stream

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(req: ChatRequest):
    return EventSourceResponse(
        generate_rag_stream(req.question, req.kb_id, req.top_k),
        media_type="text/event-stream",
    )
