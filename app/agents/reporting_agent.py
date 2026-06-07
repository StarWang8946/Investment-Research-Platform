from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from typing import Any

from psycopg import Connection

from app.skills import SkillCall, default_registry
from app.skills import research as _research_skills  # noqa: F401
from app.services.assets import export_asset
from app.services.tasks import create_task_run

from .base_agent import AgentContext, AgentTaskOutput, BaseAgent


@dataclass(frozen=True)
class ReportAgentInput:
    report_type: str
    topic: str
    template_key: str | None = None
    export_format: str | None = None
    company_code: str | None = None
    top_k: int = 8

    @classmethod
    def from_context(cls, context: AgentContext) -> "ReportAgentInput":
        payload = context.payload
        task_type = (payload.get("task_type") or "daily_report").strip().lower()
        report_type = _normalize_report_type(task_type)
        return cls(
            report_type=report_type,
            topic=payload.get("topic") or payload.get("input_text") or "今日重点研究信息",
            template_key=payload.get("template_key"),
            export_format=payload.get("export_format"),
            company_code=payload.get("company_code"),
            top_k=payload.get("top_k", 8),
        )


@dataclass(frozen=True)
class ReportAgentOutput:
    report_type: str
    asset: dict[str, Any]
    content_markdown: str
    citations: list[dict[str, Any]]
    export: dict[str, Any] | None = None
    prompt_template_used: bool = False
    template_key: str | None = None

    def to_result(self) -> dict[str, Any]:
        data = {
            "report_type": self.report_type,
            "asset": self.asset,
            "content_markdown": self.content_markdown,
            "citations": self.citations,
            "prompt_template_used": self.prompt_template_used,
            "template_key": self.template_key,
        }
        if self.export:
            data["export"] = self.export
        return data


class ReportingAgent(BaseAgent):
    name = "report_agent"
    description = "Generate reusable reporting assets such as daily reports, weekly reports, and investment briefs."

    def run(self, conn: Connection, context: AgentContext) -> dict[str, Any]:
        task_input = context.task_input
        report_input = ReportAgentInput.from_context(context)
        started = perf_counter()
        skill_name = _select_skill(report_input.report_type)
        result = default_registry.run(
            conn,
            SkillCall(
                name=skill_name,
                payload={
                    "topic": report_input.topic,
                    "top_k": report_input.top_k,
                    "company_code": report_input.company_code,
                    "template_key": report_input.template_key,
                },
            ),
        )
        export_result = None
        if report_input.export_format:
            export_result = export_asset(conn, str(result.data["asset"]["id"]), report_input.export_format)
        report_output = ReportAgentOutput(
            report_type=report_input.report_type,
            asset=result.data["asset"],
            content_markdown=result.data["content_markdown"],
            citations=result.data["citations"],
            export=export_result,
            prompt_template_used=result.data.get("prompt_template_used", False),
            template_key=result.data.get("template_key"),
        )
        output = AgentTaskOutput(
            agent=self.name,
            task_type=task_input.task_type,
            status="completed",
            skill=skill_name,
            result=report_output.to_result(),
        ).to_dict()
        if task_input.task_id:
            create_task_run(
                conn,
                task_input.task_id,
                run_type="agent",
                run_name=self.name,
                status="completed",
                input_payload={
                    "task_type": task_input.task_type,
                    "report_type": report_input.report_type,
                    "topic": report_input.topic,
                    "template_key": report_input.template_key,
                    "export_format": report_input.export_format,
                },
                output_payload={"skill": skill_name, "status": "completed", "asset_id": str(result.data["asset"]["id"])},
                duration_ms=int((perf_counter() - started) * 1000),
            )
        return output


def _normalize_report_type(task_type: str) -> str:
    if task_type in {"weekly_report", "weekly-report"}:
        return "weekly_report"
    if task_type in {"investment_brief", "investment-brief", "投决材料"}:
        return "investment_brief"
    return "daily_report"


def _select_skill(report_type: str) -> str:
    if report_type == "weekly_report":
        return "report.weekly"
    if report_type == "investment_brief":
        return "report.investment_brief"
    return "report.daily"
