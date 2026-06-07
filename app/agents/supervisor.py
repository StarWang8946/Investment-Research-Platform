from __future__ import annotations

from psycopg import Connection

from .base_agent import AgentContext
from .orchestrator_agent import OrchestratorAgent, RouteDecision, decide_route
from .registry import default_agent_registry
from .reporting_agent import ReportingAgent
from .research_agent import ResearchAgent


def register_default_agents() -> None:
    default_agent_registry.register(ResearchAgent())
    default_agent_registry.register(ReportingAgent())
    default_agent_registry.register(OrchestratorAgent(), default=True)


register_default_agents()


def route_task(conn: Connection, payload: dict, request_id: str | None = None) -> dict:
    return default_agent_registry.default().run(
        conn,
        AgentContext(payload=payload, request_id=request_id),
    )


__all__ = ["RouteDecision", "decide_route", "route_task"]
