import json
from typing import AsyncGenerator

from langchain_openai import ChatOpenAI
from langchain_chroma import Chroma

from app.config import settings
from app.services.vector_store import get_chroma_client, get_collection_name
from app.services.embedding import get_embeddings
from app.services.document_store import GLOBAL_COLLECTION

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
    question: str,
    kb_id: str = "",
    top_k: int = 4,
    doc_ids: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """Stream RAG response with COT (Chain-of-Thought) reasoning tracking.

    Supports two modes:
    - Legacy KB mode: pass kb_id to search within a knowledge-base collection.
    - Library mode: pass doc_ids to search within the global collection,
      filtered by document IDs.  If doc_ids is empty/None in library mode,
      searches all documents in the global collection.
    """
    # --- COT step 1: Understanding the question ---
    yield {"event": "cot", "data": json.dumps({
        "step": "理解问题",
        "detail": f"正在分析用户问题: 「{question}」"
    }, ensure_ascii=False)}

    # --- build vectorstore / retriever ----------------------------------
    try:
        if doc_ids:
            # Library mode: global collection with doc_id filter
            collection_name = GLOBAL_COLLECTION
        elif kb_id:
            # Legacy KB mode
            collection_name = get_collection_name(kb_id)
        else:
            # Library mode without filter: search all documents
            collection_name = GLOBAL_COLLECTION

        vectorstore = Chroma(
            client=get_chroma_client(),
            collection_name=collection_name,
            embedding_function=get_embeddings(),
        )
    except Exception as e:
        yield {"event": "error", "data": json.dumps({"message": f"Knowledge base not found: {e}"}, ensure_ascii=False)}
        return

    # --- COT step 2: Retrieving relevant documents ---
    yield {"event": "cot", "data": json.dumps({
        "step": "检索文档",
        "detail": f"正在从{'指定文档' if doc_ids else '全部文档库'}中检索相关内容 (top_k={top_k})..."
    }, ensure_ascii=False)}

    try:
        search_kwargs = {"k": top_k}
        if doc_ids:
            search_kwargs["filter"] = {"doc_id": {"$in": doc_ids}}

        retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs=search_kwargs,
        )
        docs = await retriever.ainvoke(question)
    except Exception as e:
        yield {"event": "error", "data": json.dumps({"message": f"Retrieval failed: {e}"}, ensure_ascii=False)}
        return

    if not docs:
        yield {"event": "cot", "data": json.dumps({
            "step": "检索结果",
            "detail": "未找到相关文档内容"
        }, ensure_ascii=False)}
        yield {"event": "error", "data": json.dumps({"message": "未找到相关文档内容"}, ensure_ascii=False)}
        return

    # --- COT step 3: Analyzing retrieved content ---
    source_names = []
    for doc in docs:
        name = doc.metadata.get("doc_name", doc.metadata.get("source", "未知"))
        if name not in source_names:
            source_names.append(name)

    yield {"event": "cot", "data": json.dumps({
        "step": "匹配结果",
        "detail": f"找到 {len(docs)} 个相关片段，来自 {len(source_names)} 个文档: {', '.join(source_names)}"
    }, ensure_ascii=False)}

    # Yield source information
    for doc in docs:
        source_data = {
            "doc_name": doc.metadata.get("doc_name", doc.metadata.get("source", "")),
            "chunk_text": doc.page_content[:200],
            "page": doc.metadata.get("page", ""),
        }
        yield {"event": "source", "data": json.dumps(source_data, ensure_ascii=False)}

    # --- COT step 4: Building prompt ---
    yield {"event": "cot", "data": json.dumps({
        "step": "构建提示",
        "detail": "正在将检索到的内容组装为 LLM 提示词..."
    }, ensure_ascii=False)}

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

    # --- COT step 5: Generating answer ---
    yield {"event": "cot", "data": json.dumps({
        "step": "生成回答",
        "detail": f"正在调用 LLM ({settings.llm_model_name}) 生成回答..."
    }, ensure_ascii=False)}

    try:
        async for chunk in llm.astream(messages):
            if chunk.content:
                yield {"event": "token", "data": json.dumps({"content": chunk.content}, ensure_ascii=False)}
    except Exception as e:
        yield {"event": "error", "data": json.dumps({"message": f"LLM generation failed: {e}"}, ensure_ascii=False)}
        return

    yield {"event": "cot", "data": json.dumps({
        "step": "完成",
        "detail": "回答生成完毕"
    }, ensure_ascii=False)}

    yield {"event": "done", "data": json.dumps({"message": "complete"})}
