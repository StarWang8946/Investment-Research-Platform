from __future__ import annotations

import json
import ssl
from collections.abc import Iterator
from urllib import request
from urllib.error import URLError

import certifi
from psycopg import Connection

from app.core.config import get_settings
from app.services.prompts import get_default_prompt_content, get_prompt_content, render_prompt_template

DEFAULT_SYSTEM_TEMPLATE_KEY = "llm.system.default"
DEFAULT_RAG_TEMPLATE_KEY = "research.qa.rag"


def build_rag_prompt(question: str, citations: list[dict], template: str) -> str:
    context_blocks = []
    for index, item in enumerate(citations, start=1):
        source = item.get("title") or item.get("source_id") or item.get("document_id")
        text = (item.get("chunk_text") or "").strip()
        context_blocks.append(f"[{index}] {source}\n{text}")
    context = "\n\n".join(context_blocks)
    return render_prompt_template(template, {"question": question, "context": context})


def generate_answer(
    question: str,
    citations: list[dict],
    conn: Connection | None = None,
    template_key: str = DEFAULT_RAG_TEMPLATE_KEY,
) -> tuple[str, str]:
    settings = get_settings()
    if settings.llm_base_url and settings.llm_api_key:
        try:
            prompt_template = _load_prompt_template(conn, template_key)
            system_prompt = _load_prompt_template(conn, DEFAULT_SYSTEM_TEMPLATE_KEY)
            return _call_openai_compatible(
                settings.llm_base_url,
                settings.llm_api_key,
                settings.llm_model,
                build_rag_prompt(question, citations, prompt_template),
                system_prompt=system_prompt,
            ), "llm"
        except (URLError, TimeoutError, KeyError, json.JSONDecodeError, OSError):
            pass
    return _fallback_answer(question, citations), "fallback"


def generate_answer_stream(
    question: str,
    citations: list[dict],
    conn: Connection | None = None,
    template_key: str = DEFAULT_RAG_TEMPLATE_KEY,
) -> tuple[Iterator[str], str]:
    settings = get_settings()
    if settings.llm_base_url and settings.llm_api_key:
        try:
            prompt_template = _load_prompt_template(conn, template_key)
            system_prompt = _load_prompt_template(conn, DEFAULT_SYSTEM_TEMPLATE_KEY)
            return _stream_openai_compatible(
                settings.llm_base_url,
                settings.llm_api_key,
                settings.llm_model,
                build_rag_prompt(question, citations, prompt_template),
                system_prompt=system_prompt,
            ), "llm"
        except (URLError, TimeoutError, KeyError, json.JSONDecodeError, OSError):
            pass
    return _iter_text_chunks(_fallback_answer(question, citations)), "fallback"


def generate_structured_markdown(prompt: str, conn: Connection | None = None) -> tuple[str, str]:
    settings = get_settings()
    if settings.llm_base_url and settings.llm_api_key:
        try:
            return _call_openai_compatible(
                settings.llm_base_url,
                settings.llm_api_key,
                settings.llm_model,
                prompt,
                system_prompt=_load_prompt_template(conn, DEFAULT_SYSTEM_TEMPLATE_KEY),
            ), "llm"
        except (URLError, TimeoutError, KeyError, json.JSONDecodeError, OSError):
            pass
    return "", "fallback"


def _call_openai_compatible(base_url: str, api_key: str, model: str, prompt: str, system_prompt: str) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
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


def _stream_openai_compatible(base_url: str, api_key: str, model: str, prompt: str, system_prompt: str) -> Iterator[str]:
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "stream": True,
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
    response = request.urlopen(req, timeout=30, context=context)

    def iterator() -> Iterator[str]:
        with response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                payload = json.loads(data)
                text = _extract_stream_delta(payload)
                if text:
                    yield text

    return iterator()


def _load_prompt_template(conn: Connection | None, template_key: str) -> str:
    if conn is not None:
        template = get_prompt_content(conn, template_key)
        if template:
            return template
    return get_default_prompt_content(template_key)


def _extract_stream_delta(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return ""


def _fallback_answer(question: str, citations: list[dict]) -> str:
    if not citations:
        return "未检索到足够相关的本地文档片段，暂无法基于资料回答。"

    lines = [f"问题：{question}", "", "核心结论："]
    for index, item in enumerate(citations[:3], start=1):
        snippet = " ".join((item.get("chunk_text") or "").split())[:220]
        lines.append(f"- {snippet} [{index}]")
    lines.extend(["", "待验证事项：", "- 当前为本地 RAG 草稿；配置 LLM_BASE_URL 和 LLM_API_KEY 后可生成更完整答案。"])
    return "\n".join(lines)


def _iter_text_chunks(text: str, chunk_size: int = 48) -> Iterator[str]:
    for index in range(0, len(text), chunk_size):
        yield text[index:index + chunk_size]
