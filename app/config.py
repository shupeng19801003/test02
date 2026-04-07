from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    llm_base_url: str = "http://localhost:1234/v1"
    llm_api_key: str = "lm-studio"
    llm_model_name: str = "local-model"

    # Embedding
    # Provider: "local" uses HuggingFace sentence-transformers; "api" uses OpenAI-compatible API
    embedding_provider: str = "local"
    embedding_model_name: str = "BAAI/bge-base-zh-v1.5"
    embedding_base_url: str = "http://localhost:1234/v1"
    embedding_api_key: str = "lm-studio"

    # ChromaDB
    chroma_persist_dir: str = "./data/chroma_db"

    # Upload
    upload_dir: str = "./data/uploads"
    max_file_size_mb: int = 50

    # RAG
    chunk_size: int = 500
    chunk_overlap: int = 50
    retrieval_top_k: int = 4

    # Web Search
    web_search_enabled: bool = True
    web_search_top_k: int = 3

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
