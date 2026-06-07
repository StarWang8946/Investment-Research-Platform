from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from psycopg import Connection


@dataclass(frozen=True)
class AgentTaskInput:
    task_type: str
    input_text: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    task_id: str | None = None
    asset_id: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any], request_id: str | None = None) -> "AgentTaskInput":
        task_type = (payload.get("task_type") or "qa").strip().lower()
        input_text = payload.get("input_text") or payload.get("question") or payload.get("topic")
        return cls(
            task_type=task_type,
            input_text=input_text,
            payload=payload,
            request_id=request_id,
            task_id=payload.get("task_id"),
            asset_id=payload.get("asset_id"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            **self.payload,
            "task_type": self.task_type,
            "input_text": self.input_text,
            "task_id": self.task_id,
            "asset_id": self.asset_id,
        }


@dataclass(frozen=True)
class AgentTaskOutput:
    agent: str
    task_type: str
    status: str
    result: dict[str, Any] = field(default_factory=dict)
    skill: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "agent": self.agent,
            "task_type": self.task_type,
            "status": self.status,
            "result": self.result,
        }
        if self.skill:
            data["skill"] = self.skill
        if self.metadata:
            data["metadata"] = self.metadata
        return data


@dataclass(frozen=True)
class AgentContext:
    payload: dict[str, Any]
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def task_input(self) -> AgentTaskInput:
        return AgentTaskInput.from_payload(self.payload, request_id=self.request_id)


class BaseAgent:
    name: str
    description: str

    def run(self, conn: Connection, context: AgentContext) -> dict[str, Any]:
        raise NotImplementedError
