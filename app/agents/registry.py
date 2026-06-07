from __future__ import annotations

from app.core.exceptions import AppError

from .base_agent import BaseAgent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self._default_agent: str | None = None

    def register(self, agent: BaseAgent, *, default: bool = False) -> None:
        self._agents[agent.name] = agent
        if default or self._default_agent is None:
            self._default_agent = agent.name

    def get(self, name: str) -> BaseAgent:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise AppError(4004, f"agent not found: {name}", 404) from exc

    def default(self) -> BaseAgent:
        if not self._default_agent:
            raise AppError(5002, "default agent is not registered", 500)
        return self.get(self._default_agent)

    def list(self) -> list[dict]:
        return [
            {"name": agent.name, "description": agent.description}
            for agent in self._agents.values()
        ]


default_agent_registry = AgentRegistry()
