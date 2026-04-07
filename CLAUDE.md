# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此代码库中工作时提供指导。

## 常用命令

所有命令应从项目根目录运行：

### 开发
- **安装依赖**: `pip install -r requirements.txt` (或使用虚拟环境: `.venv\Scripts\pip.exe install -r requirements.txt`)
- **启动后端服务器**: `python run.py` (运行在 http://localhost:8000)
  - 替代方案(清除缓存): `python run_fresh.py`
- **测试直接调用LLM**: `python test_direct_call.py` (LLM集成调试脚本)

### 配置
- **设置环境**: 将 `.env.example` 复制为 `.env` 并自定义：
  - `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`: OpenAI兼容的LLM端点
  - `EMBEDDING_PROVIDER`: `"local"` (HuggingFace) 或 `"api"` (OpenAI兼容)
  - `EMBEDDING_MODEL_NAME`: 默认为 `BAAI/bge-base-zh-v1.5` (中文优化)
  - `CHROMA_PERSIST_DIR`: 向量数据库存储位置
  - `UPLOAD_DIR`: 文档上传目录
  - `CHUNK_SIZE`, `CHUNK_OVERLAP`, `RETRIEVAL_TOP_K`: RAG参数
  - `WEB_SEARCH_ENABLED`, `WEB_SEARCH_TOP_K`: 网络搜索选项

## 高层架构

### 系统概览
这是一个 **RAG问答系统**，具有文档智能功能。它结合了：
1. **文档管理**: 上传、解析和组织多种文档类型
2. **向量嵌入**: 使用HuggingFace sentence-transformers或API提供商自动嵌入
3. **RAG链**: 检索增强生成，可选网络搜索融合
4. **文档审计**: 基于关键词的内容检测和合规性扫描

### 后端结构 (FastAPI)

**核心层次**:

1. **API层** (`app/routers/`)
   - `document_library.py`: 主文档CRUD操作(上传、列表、删除、移动到文件夹)
   - `chat.py`: 问答端点，支持流式SSE响应
   - `audit.py`: 文档内容审计，基于分类规则
   - 历史版本: `document.py`, `knowledge_base.py`

2. **服务层** (`app/services/`)
   - **rag_chain.py**: 核心RAG逻辑，支持网络搜索融合
     - 流式输出思维链(COT)推理步骤
     - 检索本地文档 + 可选网络搜索结果
     - 通过LLM融合两个来源生成统一答案
   - **embedding.py**: 抽象嵌入提供商(本地vs API)
   - **document_processor.py**: 解析PDF、DOCX、XLSX、PPTX、TXT、MD文件
   - **document_store.py**: 管理文档元数据(基于JSON文件)
   - **vector_store.py**: ChromaDB客户端初始化和集合管理
   - **audit_engine.py**: 基于关键词的内容审计与风险评分
   - **web_search.py**: DuckDuckGo包装器(ddgs库)

3. **配置** (`app/config.py`)
   - 使用Pydantic Settings管理环境变量
   - 类型安全的配置与默认值

4. **数据模型** (`app/models.py`)
   - API端点的请求/响应模式

### 前端结构
- **index.html**: 单页应用，包含三个主要部分：
  - 文档库: 上传、浏览、组织文件
  - Q&A聊天: 查询文档，支持流式响应
  - 审计仪表板: 查看内容审计结果
- **audit.html**: 专用审计界面(历史版本)

### 数据流

**文档上传与索引**:
1. 用户上传文件 → `document_library.py` (POST `/documents`)
2. 文件解析 → `document_processor.py` (支持多种格式)
3. 文本分块 → `chunker.py` (可配置块大小/重叠)
4. 分块嵌入 → `embedding.py` (本地转换器或API)
5. 嵌入分块存储 → ChromaDB (`vector_store.py`)
6. 元数据存储 → `data/doc_store/metadata.json`

**问答流程**:
1. 用户提交问题 → `chat.py` (POST `/chat`)
2. 问题嵌入与向量搜索 → ChromaDB (top-k检索)
3. 可选网络搜索 → `web_search.py` (DuckDuckGo)
4. 两个上下文发送给LLM → `rag_chain.py`
5. LLM通过COT步骤流式响应 → 经SSE发送到前端

**审计流程**:
1. 用户选择文档与分类 → `audit.py`
2. 从ChromaDB提取内容
3. 匹配关键词模式 → `audit_engine.py`
4. 为每个分类分配风险评分
5. 结果导出为CSV/JSON (通过 `/audit/export` 端点)

### 关键技术
- **框架**: FastAPI (异步Python网络框架)
- **向量DB**: ChromaDB (进程内，持久化到磁盘)
- **嵌入**: `sentence-transformers` (HuggingFace) 或 OpenAI兼容API
- **LLM**: OpenAI兼容API (如 LM Studio、vLLM、Claude API)
- **文档解析**: `pdfplumber`、`python-docx`、`openpyxl`、`python-pptx`、`markdown`
- **网络搜索**: `ddgs` (DuckDuckGo)
- **RAG框架**: LangChain (使用langchain-openai、langchain-chroma)

### 存储
- **向量嵌入**: `./data/chroma_db/` (ChromaDB持久化目录)
- **已上传文件**: `./data/uploads/` (原始文档文件)
- **文档元数据**: `./data/doc_store/metadata.json` (JSON清单)
- **文件夹结构**: `./data/doc_store/folders.json` (自定义文件夹组织)

### 配置与环境
- 所有设置从 `.env` 文件读取 (通过Pydantic)
- 环境变量会覆盖 `app/config.py` 中的默认值
- 关键设置：
  - `EMBEDDING_PROVIDER`: 在本地转换器或API嵌入之间选择
  - `WEB_SEARCH_ENABLED`: 在RAG中切换网络搜索融合 (默认: True)
  - `CHROMA_PERSIST_DIR`: 必须存在或可创建 (启动时自动创建)
  - LLM凭证: 确保 `LLM_BASE_URL` 和 `LLM_API_KEY` 有效

### 常见工作流

**本地开发**:
1. 确保 `.env` 指向运行中的LLM (如本地的LM Studio:1234)
2. 运行 `python run.py` 启动服务器
3. 打开浏览器访问 `http://localhost:8000`
4. 上传文档 → 自动嵌入和索引

**嵌入提供商切换**:
- 设置 `EMBEDDING_PROVIDER=local` + `EMBEDDING_MODEL_NAME=BAAI/bge-base-zh-v1.5` 以使用HuggingFace (首次运行较慢，之后速度快)
- 设置 `EMBEDDING_PROVIDER=api` + `EMBEDDING_BASE_URL` + `EMBEDDING_API_KEY` 以使用API (需要运行中的服务)

**清除缓存**:
- 运行 `python run_fresh.py` 以清除Python模块缓存并以新导入重新启动
- 当模型/服务更改未立即反映时使用

### 测试与调试
- **直接LLM测试**: `python test_direct_call.py` (LLM连接最小化测试)
- **健康检查**: GET `/api/health` (返回 `{"status": "ok"}`)
- **ChromaDB检查**: 直接使用 `chroma_persist_dir` 文件(基于SQLite)
- **文档元数据**: 检查 `data/doc_store/metadata.json` 查看上传历史
