from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.skills import SkillCall, default_registry
from app.skills import research as _research_skills  # noqa: F401

from .base_agent import AgentContext, AgentTaskOutput, BaseAgent


class ReportingAgent(BaseAgent):
    name = "report_agent"
    description = "Generate reporting assets such as daily research reports."

    def run(self, conn: Connection, context: AgentContext) -> dict[str, Any]:
        task_input = context.task_input
        payload = task_input.payload
        topic = payload.get("topic") or task_input.input_text or "今日重点研究信息"
        result = default_registry.run(
            conn,
            SkillCall(
                name="report.daily",
                payload={
                    "topic": topic,
                    "top_k": payload.get("top_k", 8),
                    "company_code": payload.get("company_code"),
                },
            ),
        )
        return AgentTaskOutput(
            agent=self.name,
            task_type=task_input.task_type,
            status="completed",
            skill="report.daily",
            result=result.data,
        ).to_dict()
