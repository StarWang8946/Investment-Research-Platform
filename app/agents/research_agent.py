from __future__ import annotations

from time import perf_counter

from typing import Any

from psycopg import Connection

from app.skills import SkillCall, default_registry
from app.skills import research as _research_skills  # noqa: F401
from app.services.tasks import create_task_run

from .base_agent import AgentContext, AgentTaskOutput, BaseAgent


class ResearchAgent(BaseAgent):
    name = "research_agent"
    description = "Handle research retrieval, QA, summaries, memos, and conclusions through research skills."

    def run(self, conn: Connection, context: AgentContext) -> dict[str, Any]:
        task_input = context.task_input
        payload = task_input.payload
        skill_name, payload_key, default_top_k = _select_skill(task_input.task_type)
        input_text = payload.get(payload_key) or task_input.input_text
        started = perf_counter()

        result = default_registry.run(
            conn,
            SkillCall(
                name=skill_name,
                payload={
                    payload_key: input_text,
                    "top_k": payload.get("top_k", default_top_k),
                    "company_code": payload.get("company_code"),
                    "doc_type": payload.get("doc_type"),
                    "template_key": payload.get("template_key"),
                    "task_id": payload.get("task_id"),
                    "asset_id": payload.get("asset_id"),
                    "request_id": context.request_id,
                },
            ),
        )
        output = AgentTaskOutput(
            agent=self.name,
            task_type=task_input.task_type,
            status="completed",
            skill=skill_name,
            result=result.data,
        ).to_dict()
        if task_input.task_id:
            create_task_run(
                conn,
                task_input.task_id,
                run_type="agent",
                run_name=self.name,
                status="completed",
                input_payload={"task_type": task_input.task_type, payload_key: input_text},
                output_payload={"skill": skill_name, "status": "completed"},
                duration_ms=int((perf_counter() - started) * 1000),
            )
        return output


def _select_skill(task_type: str) -> tuple[str, str, int]:
    if task_type in {"retrieve", "search", "research_retrieve"}:
        return "research.retrieve", "query", 8
    if task_type in {"memo", "research_memo"}:
        return "research.memo", "topic", 8
    if task_type in {"summary", "summarize", "research_summary", "摘要"}:
        return "research.summary", "topic", 8
    if task_type in {"conclusion", "research_conclusion", "研究结论"}:
        return "research.conclusion", "topic", 8
    return "research.qa", "question", 5
