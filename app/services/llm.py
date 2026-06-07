from __future__ import annotations

import json
import ssl
from urllib import request
from urllib.error import URLError

import certifi

from app.core.config import get_settings


def build_rag_prompt(question: str, citations: list[dict]) -> str:
    context_blocks = []
    for index, item in enumerate(citations, start=1):
        source = item.get("title") or item.get("source_id") or item.get("document_id")
        text = (item.get("chunk_text") or "").strip()
        context_blocks.append(f"[{index}] {source}\n{text}")
    context = "\n\n".join(context_blocks)
    return (
        "你是投资研究助理。请只基于给定资料回答问题，结论要简洁，并在关键句后标注引用编号。\n\n"
        f"问题：{question}\n\n"
        f"资料：\n{context}\n\n"
        "请输出：核心结论、依据、风险/待验证事项。"
    )


def generate_answer(question: str, citations: list[dict]) -> tuple[str, str]:
    settings = get_settings()
    if settings.llm_base_url and settings.llm_api_key:
        try:
            return _call_openai_compatible(settings.llm_base_url, settings.llm_api_key, settings.llm_model, build_rag_prompt(question, citations)), "llm"
        except (URLError, TimeoutError, KeyError, json.JSONDecodeError, OSError):
            pass
    return _fallback_answer(question, citations), "fallback"


def generate_structured_markdown(prompt: str) -> tuple[str, str]:
    settings = get_settings()
    if settings.llm_base_url and settings.llm_api_key:
        try:
            return _call_openai_compatible(settings.llm_base_url, settings.llm_api_key, settings.llm_model, prompt), "llm"
        except (URLError, TimeoutError, KeyError, json.JSONDecodeError, OSError):
            pass
    return "", "fallback"


def _call_openai_compatible(base_url: str, api_key: str, model: str, prompt: str) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是严谨的中文投资研究助理。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    context = ssl.create_default_context(cafile=certifi.where())
    with request.urlopen(req, timeout=30, context=context) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def _fallback_answer(question: str, citations: list[dict]) -> str:
    if not citations:
        return "未检索到足够相关的本地文档片段，暂无法基于资料回答。"

    lines = [f"问题：{question}", "", "核心结论："]
    for index, item in enumerate(citations[:3], start=1):
        snippet = " ".join((item.get("chunk_text") or "").split())[:220]
        lines.append(f"- {snippet} [{index}]")
    lines.extend(["", "待验证事项：", "- 当前为本地 RAG 草稿；配置 LLM_BASE_URL 和 LLM_API_KEY 后可生成更完整答案。"])
    return "\n".join(lines)
