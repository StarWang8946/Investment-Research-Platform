from __future__ import annotations

from psycopg import Connection

from app.services.assets import create_asset
from app.services.llm import generate_structured_markdown
from app.services.prompts import get_default_prompt_content, get_prompt_content, render_prompt_template
from app.services.search import answer_question, hybrid_search, save_citations

REPORT_PROMPT_KEYS = {
    "memo": "research.memo",
    "daily_report": "research.daily_report",
    "weekly_report": "research.weekly_report",
    "investment_brief": "research.investment_brief",
    "summary": "research.summary",
    "conclusion": "research.conclusion",
}


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

## 市场概览

{market_summary}

## 公告跟踪

{announcement_summary}

## 新闻动态

{news_summary}

## 研究观点

{research_viewpoints}

## 风险提示

{risks}

## 引用

{references}
"""


WEEKLY_TEMPLATE = """# {title}

## 本周重点

{answer}

## 关键进展

{evidence}

## 风险提示

{risks}

## 引用

{references}
"""


INVESTMENT_BRIEF_TEMPLATE = """# {title}

## 投决结论

{answer}

## 核心依据

{evidence}

## 风险与待验证事项

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


def generate_memo(
    conn: Connection,
    topic: str,
    top_k: int = 8,
    company_code: str | None = None,
    template_key: str | None = None,
) -> dict:
    title = f"{topic} - 研究备忘录"
    return _generate_report(
        conn,
        topic=topic,
        title=title,
        asset_type="memo",
        template=MEMO_TEMPLATE,
        top_k=top_k,
        company_code=company_code,
        template_key=template_key,
    )


def generate_daily_report(
    conn: Connection,
    topic: str,
    top_k: int = 8,
    company_code: str | None = None,
    template_key: str | None = None,
) -> dict:
    evidence_pack = extract_multi_document_evidence(conn, topic, top_k=top_k, company_code=company_code)
    references = _format_references(evidence_pack["citations"])
    sections = _build_daily_sections(evidence_pack["documents"])
    risks = "- 后续需要结合真实公告、财报和行业数据继续验证。"
    prompt_key = template_key or REPORT_PROMPT_KEYS["daily_report"]
    prompt_template = _load_prompt_template(conn, prompt_key)
    prompt = _render_daily_report_prompt(
        template=prompt_template,
        title="晨会日报",
        topic=topic,
        market_summary=sections["market_summary"],
        announcement_summary=sections["announcement_summary"],
        news_summary=sections["news_summary"],
        research_viewpoints=sections["research_viewpoints"],
        risks=risks,
        references=references,
    )
    content_markdown, provider = generate_structured_markdown(prompt, conn=conn)
    if provider == "fallback":
        content_markdown = DAILY_TEMPLATE.format(
            title="晨会日报",
            market_summary=sections["market_summary"],
            announcement_summary=sections["announcement_summary"],
            news_summary=sections["news_summary"],
            research_viewpoints=sections["research_viewpoints"],
            risks=risks,
            references=references,
        )

    asset = create_asset(
        conn,
        {
            "asset_type": "daily_report",
            "title": "晨会日报",
            "content_markdown": content_markdown,
            "summary": _daily_summary(sections),
            "company_code": company_code,
            "task_id": None,
            "sources": _build_asset_sources_from_citations(evidence_pack["citations"]),
        },
    )
    saved_citations = save_citations(conn, evidence_pack["citations"], asset_id=str(asset["id"]))
    return {
        "title": "晨会日报",
        "asset": asset,
        "content_markdown": content_markdown,
        "answer_provider": provider,
        "embedding_provider": evidence_pack["embedding_provider"],
        "citations": saved_citations,
        "evidence": evidence_pack,
        "sections": sections,
        "template_key": prompt_key,
        "prompt_template_used": bool(prompt_template),
    }


def generate_weekly_report(
    conn: Connection,
    topic: str,
    top_k: int = 8,
    company_code: str | None = None,
    template_key: str | None = None,
) -> dict:
    return _generate_report(
        conn,
        topic=topic,
        title="研究周报",
        asset_type="weekly_report",
        template=WEEKLY_TEMPLATE,
        top_k=top_k,
        company_code=company_code,
        template_key=template_key,
    )


def generate_investment_brief(
    conn: Connection,
    topic: str,
    top_k: int = 8,
    company_code: str | None = None,
    template_key: str | None = None,
) -> dict:
    return _generate_report(
        conn,
        topic=topic,
        title=f"{topic} - 投决材料",
        asset_type="investment_brief",
        template=INVESTMENT_BRIEF_TEMPLATE,
        top_k=top_k,
        company_code=company_code,
        template_key=template_key,
    )


def generate_summary(
    conn: Connection,
    topic: str,
    top_k: int = 8,
    company_code: str | None = None,
    template_key: str | None = None,
) -> dict:
    results = hybrid_search(conn, topic, top_k=top_k, company_code=company_code)
    citations = results["items"]
    references = _format_references(citations)
    evidence = _format_evidence(citations)
    prompt_key = template_key or REPORT_PROMPT_KEYS["summary"]
    prompt = _render_template_prompt(
        _load_prompt_template(conn, prompt_key),
        {
            "topic": topic,
            "context": _format_context(citations),
            "references": references,
            "evidence": evidence,
        },
    )
    content_markdown, provider = generate_structured_markdown(prompt, conn=conn)
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
        "template_key": prompt_key,
    }


def generate_research_conclusion(
    conn: Connection,
    topic: str,
    top_k: int = 8,
    company_code: str | None = None,
    template_key: str | None = None,
) -> dict:
    qa = answer_question(conn, topic, top_k=top_k, company_code=company_code)
    references = _format_references(qa["citations"])
    evidence = _format_evidence(qa["citations"])
    risks = "- 当前结论仅基于已入库资料，后续需要结合最新公告、财报和行业数据继续验证。"
    prompt_key = template_key or REPORT_PROMPT_KEYS["conclusion"]
    prompt = _render_template_prompt(
        _load_prompt_template(conn, prompt_key),
        {
            "topic": topic,
            "qa_answer": qa["answer"],
            "answer": qa["answer"],
            "references": references,
            "evidence": evidence,
            "risks": risks,
        },
    )
    content_markdown, provider = generate_structured_markdown(prompt, conn=conn)
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
        "template_key": prompt_key,
    }


def _generate_report(
    conn: Connection,
    topic: str,
    title: str,
    asset_type: str,
    template: str,
    top_k: int,
    company_code: str | None,
    template_key: str | None = None,
) -> dict:
    evidence_pack = extract_multi_document_evidence(conn, topic, top_k=top_k, company_code=company_code)
    citations = evidence_pack["citations"]
    references = _format_references(citations)
    evidence = evidence_pack["evidence_markdown"]
    risks = "- 后续需要结合真实公告、财报和行业数据继续验证。"
    qa = answer_question(conn, topic, top_k=top_k, company_code=company_code)
    prompt_key = template_key or REPORT_PROMPT_KEYS[asset_type]
    prompt_template = _load_prompt_template(conn, prompt_key)
    prompt = _render_report_prompt(
        template=prompt_template,
        topic=topic,
        title=title,
        qa_answer=qa["answer"],
        evidence=evidence,
        references=references,
        risks=risks,
    )
    content_markdown, provider = generate_structured_markdown(prompt, conn=conn)
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
            "task_id": None,
            "sources": _build_asset_sources_from_citations(citations),
        },
    )
    saved_citations = save_citations(conn, citations, asset_id=str(asset["id"]))
    return {
        "title": title,
        "asset": asset,
        "content_markdown": content_markdown,
        "answer_provider": provider if provider != "fallback" else qa["answer_provider"],
        "embedding_provider": qa["embedding_provider"],
        "citations": saved_citations,
        "evidence": evidence_pack,
        "template_key": prompt_key,
        "prompt_template_used": bool(prompt_template),
    }


def extract_multi_document_evidence(conn: Connection, topic: str, top_k: int = 8, company_code: str | None = None) -> dict:
    results = hybrid_search(conn, topic, top_k=top_k, company_code=company_code)
    citations = results["items"]
    grouped: dict[str, dict] = {}
    for item in citations:
        document_id = str(item.get("document_id"))
        group = grouped.setdefault(
            document_id,
            {
                "document_id": document_id,
                "title": item.get("title"),
                "source_id": item.get("source_id"),
                "company_code": item.get("company_code"),
                "company_name": item.get("company_name"),
                "items": [],
            },
        )
        group["items"].append(item)

    documents = []
    for group in grouped.values():
        snippets = []
        for item in group["items"][:3]:
            text = " ".join((item.get("chunk_text") or "").split())[:260]
            snippets.append(
                {
                    "chunk_id": item.get("chunk_id"),
                    "chunk_index": item.get("chunk_index"),
                    "page_no": item.get("page_no"),
                    "score": item.get("score"),
                    "text": text,
                }
            )
        documents.append({**group, "key_points": snippets})

    return {
        "topic": topic,
        "embedding_provider": results["embedding_provider"],
        "document_count": len(documents),
        "documents": documents,
        "citations": citations,
        "evidence_markdown": _format_document_evidence(documents),
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


def _format_document_evidence(documents: list[dict]) -> str:
    if not documents:
        return "- 暂无可引用资料。"
    lines = []
    citation_no = 1
    for doc in documents:
        source = doc.get("title") or doc.get("source_id") or doc.get("document_id")
        lines.append(f"- 文档：{source}")
        for point in doc["key_points"]:
            lines.append(f"  - {point['text']} [{citation_no}]")
            citation_no += 1
    return "\n".join(lines)


def _build_daily_sections(documents: list[dict]) -> dict[str, str]:
    buckets = {
        "market_summary": [],
        "announcement_summary": [],
        "news_summary": [],
        "research_viewpoints": [],
    }
    for doc in documents:
        source = (doc.get("title") or doc.get("source_id") or doc.get("document_id") or "").lower()
        target = _classify_daily_section(source)
        for point in doc["key_points"][:2]:
            buckets[target].append(f"- {point['text']}")

    return {
        key: "\n".join(value) if value else "- 暂无相关资料。"
        for key, value in buckets.items()
    }


def _classify_daily_section(source: str) -> str:
    if any(keyword in source for keyword in ("公告", "announcement", "财报", "report")):
        return "announcement_summary"
    if any(keyword in source for keyword in ("新闻", "news", "快讯")):
        return "news_summary"
    if any(keyword in source for keyword in ("观点", "深度", "strategy", "comment")):
        return "research_viewpoints"
    return "market_summary"


def _load_prompt_template(conn: Connection, template_key: str) -> str:
    return get_prompt_content(conn, template_key) or get_default_prompt_content(template_key)


def _render_template_prompt(template: str, values: dict[str, str]) -> str:
    return render_prompt_template(template, values)


def _render_report_prompt(
    template: str | None,
    topic: str,
    title: str,
    qa_answer: str,
    evidence: str,
    references: str,
    risks: str,
) -> str:
    values = {
        "topic": topic,
        "title": title,
        "qa_answer": qa_answer,
        "answer": qa_answer,
        "evidence": evidence,
        "references": references,
        "risks": risks,
    }
    return _render_template_prompt(template, values)


def _render_daily_report_prompt(
    template: str | None,
    title: str,
    topic: str,
    market_summary: str,
    announcement_summary: str,
    news_summary: str,
    research_viewpoints: str,
    risks: str,
    references: str,
) -> str:
    values = {
        "title": title,
        "topic": topic,
        "market_summary": market_summary,
        "announcement_summary": announcement_summary,
        "news_summary": news_summary,
        "research_viewpoints": research_viewpoints,
        "risks": risks,
        "references": references,
    }
    return _render_template_prompt(template, values)


def _daily_summary(sections: dict[str, str]) -> str:
    return " ".join(
        section.replace("- 暂无相关资料。", "").strip()
        for section in sections.values()
        if section.strip() and section.strip() != "- 暂无相关资料。"
    )[:500]


def _build_asset_sources_from_citations(citations: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    items: list[dict] = []
    for citation in citations:
        document_id = str(citation["document_id"])
        key = ("document", document_id)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "source_type": "document",
                "source_ref_id": document_id,
                "source_id_text": citation.get("source_id") or citation.get("title"),
                "note": citation.get("title"),
            }
        )
    return items


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
