def build_thread_id(*, encounter_id: int, user_id: int) -> str:
    return f"copilot:encounter:{encounter_id}:doctor:{user_id}"

