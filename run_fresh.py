#!/usr/bin/env python
"""Fresh startup script with no module caching."""

import sys
import os

# Remove cached modules
if 'app' in sys.modules:
    del sys.modules['app']
for key in list(sys.modules.keys()):
    if key.startswith('app.'):
        del sys.modules[key]

# Clear Python cache
import shutil
cache_dir = os.path.join(os.path.dirname(__file__), 'app', '__pycache__')
if os.path.exists(cache_dir):
    shutil.rmtree(cache_dir)

# Now import and run
import uvicorn
from app.config import settings

print(f"[STARTUP] Configuration verification:")
print(f"  web_search_enabled = {settings.web_search_enabled}")
print(f"  web_search_top_k = {settings.web_search_top_k}")
print(f"  Starting server on {settings.host}:{settings.port}")

uvicorn.run(
    "app.main:app",
    host=settings.host,
    port=settings.port,
    reload=False,
    log_level="info",
)
