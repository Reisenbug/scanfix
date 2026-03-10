from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from scanfix.models import FixResult, Issue


def _get_github_client(token: str):
    from github import Github
    return Github(token)


def create_github_issue(
    issue: Issue,
    repo_name: str,
    github_token: str,
) -> Optional[str]:
    try:
        g = _get_github_client(github_token)
        repo = g.get_repo(repo_name)

        loc = issue.file_path
        if issue.line_start:
            loc += f":{issue.line_start}"

        body = f"""## Issue Details

**Severity:** {issue.severity.value.upper()}
**Type:** {issue.issue_type.value}
**File:** `{loc}`

## Description

{issue.description}

## Suggestion

{issue.suggestion}

---
*Found by [Scanfix](https://github.com/scanfix/scanfix)*
"""
        labels = [issue.severity.value, issue.issue_type.value]
        gh_issue = repo.create_issue(
            title=f"[{issue.severity.value.upper()}] {issue.title}",
            body=body,
            labels=labels,
        )
        return gh_issue.html_url
    except Exception as e:
        from rich.console import Console
        Console().print(f"[red]Failed to create GitHub issue: {e}[/red]")
        return None


def create_github_pr(
    fix_result: FixResult,
    repo_name: str,
    github_token: str,
    repo_path: str,
    base_branch: str = "main",
) -> Optional[str]:
    if not fix_result.diff or not fix_result.success:
        return None

    try:
        branch_name = f"scanfix/{fix_result.issue.id[:8]}"

        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
            f.write(fix_result.diff)
            patch_file = f.name

        subprocess.run(
            ["git", "apply", patch_file],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        Path(patch_file).unlink(missing_ok=True)

        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"fix: {fix_result.issue.title}"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push", "origin", branch_name],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        g = _get_github_client(github_token)
        repo = g.get_repo(repo_name)

        body = f"""## Automated Fix by Scanfix

**Issue:** {fix_result.issue.title}
**Severity:** {fix_result.issue.severity.value.upper()}
**File:** `{fix_result.issue.file_path}`

### Description
{fix_result.issue.description}

### Fix Applied
{fix_result.issue.suggestion}
"""
        pr = repo.create_pull(
            title=f"fix: {fix_result.issue.title}",
            body=body,
            head=branch_name,
            base=base_branch,
        )
        return pr.html_url
    except Exception as e:
        from rich.console import Console
        Console().print(f"[red]Failed to create GitHub PR: {e}[/red]")
        return None
    finally:
        subprocess.run(
            ["git", "checkout", base_branch],
            cwd=repo_path,
            capture_output=True,
        )
