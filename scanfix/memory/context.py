from __future__ import annotations

from scanfix.models import Issue
from scanfix.memory.store import MemoryStore


def _format_fixes(fixes: list[dict]) -> str:
    parts = []
    for fix in fixes:
        parts.append(f"Issue: {fix['title']}\nDiff:\n{fix['diff']}\n")
    return "\n---\n".join(parts)


def build_agent_context(issue: Issue, store: MemoryStore) -> str:
    similar = store.get_similar_fixes(issue)
    if not similar:
        return ""
    formatted = _format_fixes(similar)
    return f"Past successful fixes for similar issues:\n{formatted}\n"
