from __future__ import annotations

from psycopg import Connection

from app.services.assets import create_asset
from app.services.llm import generate_structured_markdown
from app.services.search import answer_question, hybrid_search, save_citations


MEMO_TEMPLATE = """# {title}

## 核心结论

{answer}

## 关键依据

{evidence}

## 风险与待验证事项

{risks}

## 引用

{references}
"""


DAILY_TEMPLATE = """# {title}

## 今日重点

{answer}

## 关注线索

{evidence}

## 风险提示

{risks}

## 引用

{references}
"""


SUMMARY_TEMPLATE = """# {title}

## 摘要

{summary}

## 关键依据

{evidence}

## 引用

{references}
"""


CONCLUSION_TEMPLATE = """# {title}

## 研究结论

{conclusion}

## 核心依据

{evidence}

## 风险与待验证事项

{risks}

## 引用

{references}
"""


def generate_memo(conn: Connection, topic: str, top_k: int = 8, company_code: str | None = None) -> dict:
    title = f"{topic} - 研究备忘录"
    return _generate_report(
        conn,
        topic=topic,
        title=title,
        asset_type="memo",
        template=MEMO_TEMPLATE,
        instruction="请基于资料生成投研备忘录，突出核心结论、证据和风险，关键句必须带引用编号。",
        top_k=top_k,
        company_code=company_code,
    )


def generate_daily_report(conn: Connection, topic: str, top_k: int = 8, company_code: str | None = None) -> dict:
    return _generate_report(
        conn,
        topic=topic,
        title="研究日报",
        asset_type="daily_report",
        template=DAILY_TEMPLATE,
        instruction="请基于资料生成晨会研究日报，输出今日重点、关注线索和风险提示，关键句必须带引用编号。",
        top_k=top_k,
        company_code=company_code,
    )


def generate_summary(conn: Connection, topic: str, top_k: int = 8, company_code: str | None = None) -> dict:
    results = hybrid_search(conn, topic, top_k=top_k, company_code=company_code)
    citations = results["items"]
    references = _format_references(citations)
    evidence = _format_evidence(citations)
    prompt = (
        "请基于以下投研资料生成中文摘要，突出事实、变化、原因和待跟踪事项，关键句必须带引用编号。\n\n"
        f"主题：{topic}\n\n"
        f"资料：\n{_format_context(citations)}\n\n"
        "请输出 Markdown，包含“摘要”和“待跟踪事项”。不要编造资料外的信息。"
    )
    content_markdown, provider = generate_structured_markdown(prompt)
    if provider == "fallback":
        content_markdown = SUMMARY_TEMPLATE.format(
            title=f"{topic} - 资料摘要",
            summary=_fallback_summary(topic, citations),
            evidence=evidence,
            references=references,
        )
    return {
        "topic": topic,
        "content_markdown": content_markdown,
        "answer_provider": provider,
        "embedding_provider": results["embedding_provider"],
        "citations": citations,
    }


def generate_research_conclusion(conn: Connection, topic: str, top_k: int = 8, company_code: str | None = None) -> dict:
    qa = answer_question(conn, topic, top_k=top_k, company_code=company_code)
    references = _format_references(qa["citations"])
    evidence = _format_evidence(qa["citations"])
    risks = "- 当前结论仅基于已入库资料，后续需要结合最新公告、财报和行业数据继续验证。"
    prompt = (
        "请基于投研资料形成可执行的研究结论，区分结论、依据、风险和待验证事项，关键句必须带引用编号。\n\n"
        f"主题：{topic}\n\n"
        f"问答草稿：\n{qa['answer']}\n\n"
        f"引用资料：\n{references}\n\n"
        "请输出 Markdown，不要编造资料外的信息。"
    )
    content_markdown, provider = generate_structured_markdown(prompt)
    if provider == "fallback":
        content_markdown = CONCLUSION_TEMPLATE.format(
            title=f"{topic} - 研究结论",
            conclusion=qa["answer"],
            evidence=evidence,
            risks=risks,
            references=references,
        )
    return {
        "topic": topic,
        "content_markdown": content_markdown,
        "answer_provider": provider if provider != "fallback" else qa["answer_provider"],
        "embedding_provider": qa["embedding_provider"],
        "citations": qa["citations"],
    }


def _generate_report(
    conn: Connection,
    topic: str,
    title: str,
    asset_type: str,
    template: str,
    instruction: str,
    top_k: int,
    company_code: str | None,
) -> dict:
    qa = answer_question(conn, topic, top_k=top_k, company_code=company_code)
    references = _format_references(qa["citations"])
    evidence = _format_evidence(qa["citations"])
    risks = "- 后续需要结合真实公告、财报和行业数据继续验证。"
    prompt = (
        f"{instruction}\n\n"
        f"主题：{topic}\n\n"
        f"已有问答草稿：\n{qa['answer']}\n\n"
        f"引用资料：\n{references}\n\n"
        "请输出 Markdown，保留标题层级，不要编造资料外的信息。"
    )
    content_markdown, provider = generate_structured_markdown(prompt)
    if provider == "fallback":
        content_markdown = template.format(
            title=title,
            answer=qa["answer"],
            evidence=evidence,
            risks=risks,
            references=references,
        )

    asset = create_asset(
        conn,
        {
            "asset_type": asset_type,
            "title": title,
            "content_markdown": content_markdown,
            "summary": qa["answer"][:500],
            "company_code": company_code,
        },
    )
    citations = save_citations(conn, qa["citations"], asset_id=str(asset["id"]))
    return {
        "title": title,
        "asset": asset,
        "content_markdown": content_markdown,
        "answer_provider": provider if provider != "fallback" else qa["answer_provider"],
        "embedding_provider": qa["embedding_provider"],
        "citations": citations,
    }


def _format_evidence(citations: list[dict]) -> str:
    if not citations:
        return "- 暂无可引用资料。"
    return "\n".join(f"- {item.get('chunk_text', '').strip()[:220]} [{index}]" for index, item in enumerate(citations[:5], start=1))


def _format_references(citations: list[dict]) -> str:
    if not citations:
        return "- 暂无引用。"
    lines = []
    for index, item in enumerate(citations, start=1):
        source = item.get("title") or item.get("source_id") or item.get("document_id")
        lines.append(f"- [{index}] {source} / chunk={item.get('chunk_id')}")
    return "\n".join(lines)


def _format_context(citations: list[dict]) -> str:
    if not citations:
        return "暂无资料。"
    blocks = []
    for index, item in enumerate(citations, start=1):
        source = item.get("title") or item.get("source_id") or item.get("document_id")
        text = " ".join((item.get("chunk_text") or "").split())
        blocks.append(f"[{index}] {source}\n{text}")
    return "\n\n".join(blocks)


def _fallback_summary(topic: str, citations: list[dict]) -> str:
    if not citations:
        return f"围绕“{topic}”未检索到足够相关的本地资料，暂无法生成摘要。"
    lines = [f"围绕“{topic}”检索到以下要点："]
    for index, item in enumerate(citations[:5], start=1):
        snippet = " ".join((item.get("chunk_text") or "").split())[:220]
        lines.append(f"- {snippet} [{index}]")
    return "\n".join(lines)
