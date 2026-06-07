from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from psycopg import Connection

from app.skills import default_registry

from .base_agent import AgentContext, BaseAgent
from .registry import AgentRegistry, default_agent_registry


@dataclass(frozen=True)
class RouteDecision:
    task_type: str
    agent: str
    skill: str
    reason: str


class OrchestratorAgent(BaseAgent):
    name = "orchestrator_agent"
    description = "Route user tasks to the right specialist agent and aggregate the result."

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self.registry = registry or default_agent_registry

    def run(self, conn: Connection, context: AgentContext) -> dict[str, Any]:
        decision = decide_route(context.payload)
        response: dict[str, Any] = {
            "decision": asdict(decision),
            "available_agents": self.registry.list(),
            "available_skills": default_registry.list(),
        }
        if decision.agent in {"research_agent", "report_agent"}:
            routed_payload = {
                **context.payload,
                "task_type": decision.task_type,
            }
            agent_result = self.registry.get(decision.agent).run(
                conn,
                AgentContext(
                    payload=routed_payload,
                    request_id=context.request_id,
                    metadata={**context.metadata, "decision": asdict(decision)},
                ),
            )
            response["result"] = agent_result["result"]
        return response


def decide_route(payload: dict) -> RouteDecision:
    task_type = (payload.get("task_type") or "").strip().lower()
    text = (payload.get("question") or payload.get("topic") or payload.get("input_text") or "").strip()

    if task_type in {"retrieve", "search", "research_retrieve"} or "检索" in text:
        return RouteDecision("retrieve", "research_agent", "research.retrieve", "retrieval task")
    if task_type in {"qa", "question", "ask"} or any(keyword in text for keyword in ("什么", "如何", "为什么", "是否", "？", "?")):
        return RouteDecision("qa", "research_agent", "research.qa", "question-like input")
    if task_type in {"memo", "research_memo"} or "备忘录" in text:
        return RouteDecision("memo", "research_agent", "research.memo", "memo task")
    if task_type in {"summary", "summarize", "research_summary"} or "摘要" in text:
        return RouteDecision("summary", "research_agent", "research.summary", "summary task")
    if task_type in {"conclusion", "research_conclusion"} or "研究结论" in text:
        return RouteDecision("conclusion", "research_agent", "research.conclusion", "research conclusion task")
    if task_type in {"daily_report", "daily-report", "report"} or "日报" in text:
        return RouteDecision("daily_report", "report_agent", "report.daily", "daily report task")
    if task_type in {"ingest", "document_ingest"} or "入库" in text:
        return RouteDecision("ingest", "document_agent", "document.ingest", "document ingest task")
    return RouteDecision("qa", "research_agent", "research.qa", "default route")
