import uvicorn
from app.config import settings

if __name__ == "__main__":
    # Verify configuration at startup
    print(f"[STARTUP] web_search_enabled = {settings.web_search_enabled}")
    print(f"[STARTUP] web_search_top_k = {settings.web_search_top_k}")

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,  # Disable auto-reload to avoid caching issues
    )
