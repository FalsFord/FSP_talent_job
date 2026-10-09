"""Реестр генераторов заданий."""
from __future__ import annotations

from app.tasks.generators.approach_gen import approach_generators
from app.tasks.generators.java_gen import JAVA_GENERATORS
from app.tasks.generators.python_gen import PYTHON_GENERATORS
from app.tasks.generators.sql_gen import SQL_GENERATORS
from app.tasks.types import GRADE_INDEX, GeneratorDef

ALL_GENERATORS: list[GeneratorDef] = [*SQL_GENERATORS, *PYTHON_GENERATORS, *JAVA_GENERATORS, *approach_generators()]
REGISTRY: dict[str, GeneratorDef] = {g.id: g for g in ALL_GENERATORS}


def get_generator(gid: str) -> GeneratorDef:
    return REGISTRY[gid]


def eligible(language: str, grade: str, *, code_exec: bool, java_ok: bool) -> list[GeneratorDef]:
    """Генераторы, доступные для языка и грейда. Задания с исполнением кода — только если раннер включён."""
    out = []
    for g in ALL_GENERATORS:
        if g.language != language or grade not in g.grades:
            continue
        if g.needs_code_exec and not (code_exec and (g.language != "java" or java_ok)):
            continue
        out.append(g)
    return out
