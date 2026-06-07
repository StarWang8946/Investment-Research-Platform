from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from psycopg import Connection


@dataclass(frozen=True)
class SkillCall:
    name: str
    payload: dict


@dataclass(frozen=True)
class SkillResult:
    name: str
    data: dict


SkillHandler = Callable[[Connection, dict], dict]


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    handler: SkillHandler


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def list(self) -> list[dict]:
        return [{"name": skill.name, "description": skill.description} for skill in self._skills.values()]

    def run(self, conn: Connection, call: SkillCall) -> SkillResult:
        skill = self._skills[call.name]
        return SkillResult(name=skill.name, data=skill.handler(conn, call.payload))


default_registry = SkillRegistry()
