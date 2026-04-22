#!/usr/bin/env python3
"""
RAG 对比测试脚本
测试 LLM 在有无 RAG 知识库增强情况下的回答差异
"""
import requests
import json
import sys

LLM_API = "http://127.0.0.1:3000/api/chat"
RAG_API = "http://127.0.0.1:3004/api/retrieve"

def get_llm_response(question):
    """获取纯 LLM 回答（无 RAG）"""
    print("\n" + "="*60)
    print("📤 问题: " + question)
    print("="*60)

    response = requests.post(
        LLM_API,
        json={"message": question},
        stream=True,
        timeout=30
    )

    print("\n🤖 LLM 回答（无 RAG）:")
    print("-" * 60)
    answer = ""
    for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
        if chunk:
            print(chunk, end="", flush=True)
            answer += chunk
    print("\n")
    return answer

def get_rag_context(question, top_k=3):
    """从 RAG 知识库检索相关内容"""
    response = requests.post(
        RAG_API,
        json={"query": question, "top_k": top_k},
        timeout=10
    )
    data = response.json()
    return data.get("results", [])

def get_rag_enhanced_response(question):
    """获取 RAG 增强的 LLM 回答"""
    print("\n" + "="*60)
    print("📤 问题: " + question)
    print("="*60)

    context_results = get_rag_context(question, top_k=3)

    if context_results:
        print("\n📚 RAG 检索到的知识:")
        print("-" * 60)
        context_text = ""
        for i, result in enumerate(context_results, 1):
            print(f"\n【相关文档 {i}】(相似度: {result.get('score', 0):.4f})")
            print(f"问题: {result.get('question', 'N/A')}")
            print(f"回答: {result.get('answer', 'N/A')[:300]}...")
            context_text += f"\n参考：{result.get('question', '')} - {result.get('answer', '')}"
    else:
        print("\n⚠️ 未从 RAG 知识库检索到相关内容")
        context_text = ""

    enhanced_question = f"""基于以下参考资料回答问题。如果参考资料中的信息不足以回答问题，请结合你的知识给出完整回答。

参考资料：
{context_text}

问题：{question}"""

    response = requests.post(
        LLM_API,
        json={"message": enhanced_question},
        stream=True,
        timeout=30
    )

    print("\n🤖 LLM 回答（RAG 增强）:")
    print("-" * 60)
    answer = ""
    for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
        if chunk:
            print(chunk, end="", flush=True)
            answer += chunk
    print("\n")

    return answer

def main():
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        print("\n" + "="*60)
        print("🔍 RAG 对比测试工具")
        print("="*60)
        print("\n使用方法:")
        print("  python3 test_rag.py <问题>")
        print("\n示例:")
        print("  python3 test_rag.py 什么是闭包？")
        print("  python3 test_rag.py 解释一下RESTful API")
        print("  python3 test_rag.py C++中的lambda是什么？")
        print("\n或输入问题进行测试：")
        question = input("\n请输入问题: ").strip()

    if not question:
        print("问题不能为空！")
        return

    print("\n" + "🎯"*25)
    print("测试: " + question)
    print("🎯"*25)

    print("\n\n" + "🔴"*20 + " 测试 1: 无 RAG 增强 " + "🔴"*20)
    get_llm_response(question)

    input("\n按 Enter 键继续测试 RAG 增强模式...")

    print("\n\n" + "🟢"*20 + " 测试 2: RAG 增强 " + "🟢"*20)
    get_rag_enhanced_response(question)

    print("\n" + "="*60)
    print("✅ 对比测试完成！")
    print("="*60)

if __name__ == "__main__":
    main()
