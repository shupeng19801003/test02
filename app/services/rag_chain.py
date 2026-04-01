import json
from typing import AsyncGenerator

from langchain_openai import ChatOpenAI
from langchain_chroma import Chroma

from app.config import settings
from app.services.vector_store import get_chroma_client, get_collection_name
from app.services.embedding import get_embeddings

SYSTEM_PROMPT = """你是一个智能问答助手。请根据以下提供的参考资料来回答用户的问题。

规则：
1. 仅基于提供的参考资料回答问题
2. 如果参考资料中没有相关信息，请如实告知用户
3. 在回答中引用来源文档名称
4. 使用清晰、结构化的方式组织回答

参考资料：
{context}
"""


def _build_context(docs: list) -> str:
    parts = []
    for i, doc in enumerate(docs):
        source = doc.metadata.get("doc_name", doc.metadata.get("source", "未知"))
        page = doc.metadata.get("page", "")
        location = f", 第{page}页" if page else ""
        parts.append(f"[来源: {source}{location}]\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


async def generate_rag_stream(
    question: str, kb_id: str, top_k: int
) -> AsyncGenerator[str, None]:
    # Retrieve relevant chunks
    try:
        vectorstore = Chroma(
            client=get_chroma_client(),
            collection_name=get_collection_name(kb_id),
            embedding_function=get_embeddings(),
        )
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'message': f'Knowledge base not found: {e}'}, ensure_ascii=False)}\n\n"
        return

    try:
        retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": top_k},
        )
        docs = await retriever.ainvoke(question)
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'message': f'Retrieval failed: {e}'}, ensure_ascii=False)}\n\n"
        return

    if not docs:
        yield f"event: error\ndata: {json.dumps({'message': '未找到相关文档内容'}, ensure_ascii=False)}\n\n"
        return

    # Yield source information
    for doc in docs:
        source_data = {
            "doc_name": doc.metadata.get("doc_name", doc.metadata.get("source", "")),
            "chunk_text": doc.page_content[:200],
            "page": doc.metadata.get("page", ""),
        }
        yield f"event: source\ndata: {json.dumps(source_data, ensure_ascii=False)}\n\n"

    # Build prompt and stream LLM response
    context = _build_context(docs)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(context=context)},
        {"role": "user", "content": question},
    ]

    llm = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model_name,
        streaming=True,
    )

    try:
        async for chunk in llm.astream(messages):
            if chunk.content:
                yield f"event: token\ndata: {json.dumps({'content': chunk.content}, ensure_ascii=False)}\n\n"
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'message': f'LLM generation failed: {e}'}, ensure_ascii=False)}\n\n"
        return

    yield f"event: done\ndata: {json.dumps({'message': 'complete'})}\n\n"
