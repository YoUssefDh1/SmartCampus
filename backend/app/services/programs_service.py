"""Catalogue : source TEMPORAIRE = données de démonstration (data/demo/programs.json).
Le Membre 3 remplacera cette source par la base PostgreSQL (SA-20)."""
import json
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.schemas.common import Page
from app.schemas.program import Program


def _demo_dir() -> Path:
    custom = get_settings().demo_data_dir
    return Path(custom) if custom else Path(__file__).resolve().parents[3] / "data" / "demo"


@lru_cache
def _load() -> list[Program]:
    return [Program(**p) for p in json.loads((_demo_dir() / "programs.json").read_text(encoding="utf-8"))]


def list_programs(school: str | None, level: str | None, page: int, size: int) -> Page[Program]:
    items = [p for p in _load()
             if (not school or p.school.lower() == school.lower())
             and (not level or p.level.lower() == level.lower())]
    start = (page - 1) * size
    return Page[Program](items=items[start:start + size], total=len(items), page=page, size=size)


def get_program(program_id: str) -> Program:
    for p in _load():
        if p.id == program_id:
            return p
    raise NotFoundError("Formation introuvable.")
