from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from scanfix.models import FixResult, Issue
from scanfix.memory.store import MemoryStore
from scanfix.memory.context import build_agent_context


def build_task_description(issue: Issue, repo_path: str, context: str = "") -> str:
    loc = issue.file_path
    if issue.line_start:
        loc += f" (lines {issue.line_start}-{issue.line_end})"

    parts = []
    if context:
        parts.append(context)

    parts.append(f"""Fix the following {issue.severity.value} severity {issue.issue_type.value} issue in the repository at {repo_path}.

Issue: {issue.title}
File: {loc}

Description:
{issue.description}

Suggested fix:
{issue.suggestion}

Please apply the fix directly to the file. Make minimal, focused changes that address the issue.
""")
    return "\n".join(parts)


def capture_git_diff(repo_path: str) -> str:
    result = subprocess.run(
        ["git", "diff"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return result.stdout


def reset_git_state(repo_path: str) -> None:
    subprocess.run(
        ["git", "checkout", "--", "."],
        cwd=repo_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "clean", "-fd"],
        cwd=repo_path,
        capture_output=True,
    )


def fix_issue(
    issue: Issue,
    repo_path: str,
    output_dir: str,
    memory_store: Optional[MemoryStore] = None,
) -> FixResult:
    context = ""
    if memory_store:
        context = build_agent_context(issue, memory_store)

    task_description = build_task_description(issue, repo_path, context)
    diff = ""

    try:
        from minisweagent.agents.default import DefaultAgent

        agent = DefaultAgent()
        agent.run(task_description)

        diff = capture_git_diff(repo_path)

        if diff:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            patch_path = out / f"{issue.id[:8]}.patch"
            patch_path.write_text(diff)

        result = FixResult(
            issue=issue,
            diff=diff,
            success=bool(diff),
            error_message=None if diff else "No changes made by agent",
        )

        if memory_store:
            memory_store.mark_fixed(issue.id, result, agent_context=context)

        return result

    except Exception as e:
        result = FixResult(
            issue=issue,
            diff="",
            success=False,
            error_message=str(e),
        )
        return result
    finally:
        reset_git_state(repo_path)


def fix_issues(
    issues: list[Issue],
    repo_path: str,
    output_dir: str,
    memory_store: Optional[MemoryStore] = None,
) -> list[FixResult]:
    results = []
    for issue in issues:
        result = fix_issue(issue, repo_path, output_dir, memory_store)
        results.append(result)
    return results
