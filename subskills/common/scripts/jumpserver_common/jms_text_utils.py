from __future__ import annotations

from typing import Any


def lower_text(value: Any) -> str:
    return str(value or "").strip().lower()


def text(value: Any) -> str:
    return str(value or "").strip()


def value_from_path(item: dict[str, Any], path: str) -> Any:
    current: Any = item
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def exact_first_filter(items: list[dict[str, Any]], expected: Any, *paths: str) -> list[dict[str, Any]]:
    wanted = lower_text(expected)
    if not wanted:
        return items
    exact_matches: list[dict[str, Any]] = []
    partial_matches: list[dict[str, Any]] = []
    for item in items:
        values = [value_from_path(item, path) for path in paths]
        text_values = [lower_text(value) for value in values if value not in {None, ""}]
        if wanted in text_values:
            exact_matches.append(item)
        elif any(wanted in value for value in text_values):
            partial_matches.append(item)
    return exact_matches or partial_matches
