from __future__ import annotations

from collections.abc import Callable
from typing import Any

from generation.generate import run_section_generation

GenerationStrategy = Callable[..., Any]

GENERATION_STRATEGIES: dict[str, GenerationStrategy] = {
    "single_call_per_section": run_section_generation,
}

STEP_STRATEGIES: dict[str, dict[str, Callable[..., Any]]] = {
    "generation": GENERATION_STRATEGIES,
}


def get_generation_strategy(name: str) -> GenerationStrategy:
    strategy = GENERATION_STRATEGIES.get(name)
    if strategy is None:
        raise ValueError(f"unknown_generation_strategy: {name}")
    return strategy
