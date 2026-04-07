#!/usr/bin/env python
"""Direct test of generate_rag_stream to verify it works and shows new code."""

import asyncio
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

async def test():
    # Force fresh import
    import importlib
    import app.services.rag_chain as rag_module
    importlib.reload(rag_module)

    generate_rag_stream = rag_module.generate_rag_stream

    print("=" * 70)
    print("[直接调用测试] 这应该显示所有的COT步骤包括'开始RAG流程'")
    print("=" * 70 + "\n")

    async for event in generate_rag_stream("Python是什么编程语言", top_k=1):
        if event['event'] == 'cot':
            data = json.loads(event['data'])
            print(f"[COT] {data['step']}: {data['detail'][:50]}")
        elif event['event'] == 'source':
            data = json.loads(event['data'])
            print(f"[来源] {data.get('doc_name', 'unknown')}")
        elif event['event'] == 'token':
            data = json.loads(event['data'])
            print(data['content'], end='', flush=True)
        elif event['event'] == 'done':
            print("\n[完成]")

if __name__ == "__main__":
    asyncio.run(test())
