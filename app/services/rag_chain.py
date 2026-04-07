import json
import logging
from typing import AsyncGenerator

from langchain_openai import ChatOpenAI
from langchain_chroma import Chroma

from app.config import settings
from app.services.vector_store import get_chroma_client, get_collection_name
from app.services.embedding import get_embeddings
from app.services.document_store import GLOBAL_COLLECTION
from app.services.web_search import search_web, format_web_results

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# ---------- System prompt for hybrid (web + RAG) fusion ----------

SYSTEM_PROMPT = """你是一个智能问答助手。你将获得两类参考资料：来自互联网的最新公开信息，以及来自本地文档库的专业资料。

请遵守以下规则生成回答：
1. **综合两类来源**：先参考网络信息了解最新背景，再以本地文档资料为权威依据进行修正和完善。
2. **冲突处理**：当网络信息与本地文档存在矛盾时，以本地文档为准，并指出差异。
3. **来源标注**：在回答中明确标注信息来源（"据网络信息"或"据文档《XXX》"）。
4. **如实说明**：如果两类来源都没有相关信息，请如实告知用户。
5. 使用清晰、结构化的方式组织回答，确保最终答案统一、准确、没有矛盾。

--- 网络参考信息 ---
{web_context}

--- 本地文档资料 ---
{local_context}
"""

# Fallback prompt when web search is disabled or returns nothing
SYSTEM_PROMPT_LOCAL_ONLY = """你是一个智能问答助手。请根据以下提供的参考资料来回答用户的问题。

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
    """Stream RAG response with web search + local RAG hybrid retrieval.

    Flow:
    1. Web search for latest public information
    2. Local RAG retrieval from vector database
    3. LLM fuses both sources into a unified answer
    """
    # TEST: Verify function is being called
    yield {"event": "cot", "data": json.dumps({
        "step": "开始RAG流程",
        "detail": f"generate_rag_stream已被调用，web_search_enabled={settings.web_search_enabled}"
    }, ensure_ascii=False)}

    # --- COT step 1: Understanding the question ---
    yield {"event": "cot", "data": json.dumps({
        "step": "理解问题",
        "detail": f"正在分析用户问题: 「{question}」"
    }, ensure_ascii=False)}

    # --- COT step 2: Web search ---
    web_results = []
    web_context = ""
    logger.info(f"RAG: BEFORE web search check: enabled={settings.web_search_enabled}")

    # Mark that we're about to check web search
    yield {"event": "cot", "data": json.dumps({
        "step": "DEBUG",
        "detail": f"web_search_enabled={settings.web_search_enabled}"
    }, ensure_ascii=False)}

    if settings.web_search_enabled:
        logger.info("RAG: Starting web search...")
        yield {"event": "cot", "data": json.dumps({
            "step": "联网搜索",
            "detail": f"正在联网搜索最新公开信息 (top_k={settings.web_search_top_k})..."
        }, ensure_ascii=False)}

        try:
            web_results = await search_web(question, max_results=settings.web_search_top_k)
            logger.info(f"RAG: Web search completed, got {len(web_results)} results")
        except Exception as e:
            logger.error(f"RAG: Web search failed: {e}", exc_info=True)
            web_results = []
        web_context = format_web_results(web_results)

        if web_results:
            yield {"event": "cot", "data": json.dumps({
                "step": "联网搜索",
                "detail": f"获取到 {len(web_results)} 条网络结果"
            }, ensure_ascii=False)}
            # Yield web sources
            for wr in web_results:
                yield {"event": "source", "data": json.dumps({
                    "doc_name": f"🌐 {wr.title}",
                    "chunk_text": wr.snippet[:200],
                    "page": "",
                    "url": wr.url,
                    "source_type": "web",
                }, ensure_ascii=False)}
        else:
            yield {"event": "cot", "data": json.dumps({
                "step": "联网搜索",
                "detail": "未获取到网络结果，将仅基于本地文档回答"
            }, ensure_ascii=False)}

    # --- COT step 3: Local RAG retrieval ---
    yield {"event": "cot", "data": json.dumps({
        "step": "检索文档",
        "detail": f"正在从{'指定文档' if doc_ids else '全部文档库'}中检索相关内容 (top_k={top_k})..."
    }, ensure_ascii=False)}

    try:
        if doc_ids:
            collection_name = GLOBAL_COLLECTION
        elif kb_id:
            collection_name = get_collection_name(kb_id)
        else:
            collection_name = GLOBAL_COLLECTION

        vectorstore = Chroma(
            client=get_chroma_client(),
            collection_name=collection_name,
            embedding_function=get_embeddings(),
        )
    except Exception as e:
        yield {"event": "error", "data": json.dumps({"message": f"Knowledge base not found: {e}"}, ensure_ascii=False)}
        return

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

    # --- COT step 4: Analyze retrieved content ---
    local_context = ""
    if docs:
        source_names = []
        for doc in docs:
            name = doc.metadata.get("doc_name", doc.metadata.get("source", "未知"))
            if name not in source_names:
                source_names.append(name)

        yield {"event": "cot", "data": json.dumps({
            "step": "匹配结果",
            "detail": f"找到 {len(docs)} 个相关片段，来自 {len(source_names)} 个文档: {', '.join(source_names)}"
        }, ensure_ascii=False)}

        # Yield local doc sources
        for doc in docs:
            source_data = {
                "doc_name": doc.metadata.get("doc_name", doc.metadata.get("source", "")),
                "chunk_text": doc.page_content[:200],
                "page": doc.metadata.get("page", ""),
                "source_type": "local",
            }
            yield {"event": "source", "data": json.dumps(source_data, ensure_ascii=False)}

        local_context = _build_context(docs)
    else:
        yield {"event": "cot", "data": json.dumps({
            "step": "匹配结果",
            "detail": "本地文档库中未找到相关内容"
        }, ensure_ascii=False)}

    # If neither source has content, report error
    if not web_context and not local_context:
        yield {"event": "error", "data": json.dumps({"message": "未找到相关信息（网络和本地文档均无结果）"}, ensure_ascii=False)}
        return

    # --- COT step 5: Building prompt ---
    yield {"event": "cot", "data": json.dumps({
        "step": "构建提示",
        "detail": "正在融合网络信息与本地文档，组装 LLM 提示词..."
            if web_context
            else "正在将检索到的本地文档内容组装为 LLM 提示词..."
    }, ensure_ascii=False)}

    # Choose prompt based on available sources
    if web_context:
        system_content = SYSTEM_PROMPT.format(
            web_context=web_context,
            local_context=local_context if local_context else "（未检索到相关本地文档）",
        )
    else:
        system_content = SYSTEM_PROMPT_LOCAL_ONLY.format(
            context=local_context,
        )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": question},
    ]

    llm = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model_name,
        streaming=True,
    )

    # --- COT step 6: Generating answer ---
    yield {"event": "cot", "data": json.dumps({
        "step": "生成回答",
        "detail": f"正在调用 LLM ({settings.llm_model_name}) 融合生成统一回答..."
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
