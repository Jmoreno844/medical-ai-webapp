from __future__ import annotations

import re
import uuid


THREAD_ID_PATTERN = re.compile(
    r"^copilot:encounter:(?P<encounter_id>\d+):doctor:(?P<user_id>\d+):chat:(?P<chat_id>[0-9a-fA-F-]+)$"
)


def build_thread_id(*, encounter_id: int, user_id: int) -> str:
    return f"copilot:encounter:{encounter_id}:doctor:{user_id}:chat:{uuid.uuid4()}"


def parse_thread_id(thread_id: str) -> tuple[int, int] | None:
    match = THREAD_ID_PATTERN.match(thread_id or "")
    if not match:
        return None
    try:
        uuid.UUID(match.group("chat_id"))
    except ValueError:
        return None
    return int(match.group("encounter_id")), int(match.group("user_id"))


def thread_belongs_to_scope(*, thread_id: str, encounter_id: int, user_id: int) -> bool:
    scope = parse_thread_id(thread_id)
    if scope is None:
        return False
    return scope == (encounter_id, user_id)
