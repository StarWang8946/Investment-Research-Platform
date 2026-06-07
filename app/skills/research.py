from __future__ import annotations

from psycopg import Connection

from app.services.reports import generate_daily_report, generate_memo, generate_research_conclusion, generate_summary
from app.services.search import execute_qa_task, hybrid_search
from app.skills.registry import Skill, default_registry


def retrieve_skill(conn: Connection, payload: dict) -> dict:
    return hybrid_search(
        conn,
        payload["query"],
        top_k=payload.get("top_k", 8),
        company_code=payload.get("company_code"),
        doc_type=payload.get("doc_type"),
    )


def qa_skill(conn: Connection, payload: dict) -> dict:
    return execute_qa_task(
        conn,
        payload["question"],
        top_k=payload.get("top_k", 5),
        company_code=payload.get("company_code"),
        task_id=payload.get("task_id"),
        asset_id=payload.get("asset_id"),
        request_id=payload.get("request_id"),
    )


def memo_skill(conn: Connection, payload: dict) -> dict:
    return generate_memo(
        conn,
        payload["topic"],
        top_k=payload.get("top_k", 8),
        company_code=payload.get("company_code"),
    )


def summary_skill(conn: Connection, payload: dict) -> dict:
    return generate_summary(
        conn,
        payload["topic"],
        top_k=payload.get("top_k", 8),
        company_code=payload.get("company_code"),
    )


def conclusion_skill(conn: Connection, payload: dict) -> dict:
    return generate_research_conclusion(
        conn,
        payload["topic"],
        top_k=payload.get("top_k", 8),
        company_code=payload.get("company_code"),
    )


def daily_report_skill(conn: Connection, payload: dict) -> dict:
    return generate_daily_report(
        conn,
        payload.get("topic") or "今日重点研究信息",
        top_k=payload.get("top_k", 8),
        company_code=payload.get("company_code"),
    )


def register_research_skills() -> None:
    default_registry.register(
        Skill(
            name="research.retrieve",
            description="Retrieve relevant document chunks for a research query.",
            handler=retrieve_skill,
        )
    )
    default_registry.register(
        Skill(
            name="research.qa",
            description="Run retrieval augmented QA with task tracking and citations.",
            handler=qa_skill,
        )
    )
    default_registry.register(
        Skill(
            name="research.memo",
            description="Generate a structured research memo and save it as a research asset.",
            handler=memo_skill,
        )
    )
    default_registry.register(
        Skill(
            name="research.summary",
            description="Summarize retrieved research materials for a topic.",
            handler=summary_skill,
        )
    )
    default_registry.register(
        Skill(
            name="research.conclusion",
            description="Generate a research conclusion from retrieved evidence and QA output.",
            handler=conclusion_skill,
        )
    )
    default_registry.register(
        Skill(
            name="report.daily",
            description="Generate a structured daily research report and save it as a research asset.",
            handler=daily_report_skill,
        )
    )


register_research_skills()
