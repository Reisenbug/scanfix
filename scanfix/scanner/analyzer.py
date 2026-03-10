from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from openai import OpenAI
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from scanfix.config import Config
from scanfix.models import Issue, IssueReport, IssueType, Severity
from scanfix.scanner.chunker import FileChunk, chunk_file
from scanfix.scanner.walker import iter_repo_files

from datetime import datetime


SYSTEM_PROMPT = """\
You are a senior software engineer performing a security and quality audit.
Analyze the provided code chunk and identify issues.
Return ONLY a JSON array of issue objects. If no issues found, return [].

Each issue object must have these fields:
- title: short descriptive title (string)
- description: detailed explanation (string)
- file_path: the file being analyzed (string)
- line_start: approximate starting line number (integer or null)
- line_end: approximate ending line number (integer or null)
- severity: one of "critical", "high", "medium", "low"
- issue_type: one of "bug", "security", "performance", "style", "other"
- suggestion: concrete fix suggestion (string)

Return only valid JSON. No markdown, no explanation, just the JSON array."""


def _parse_issues_json(text: str) -> list[dict]:
    text = text.strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def _dict_to_issue(d: dict) -> Optional[Issue]:
    try:
        severity = Severity(d.get("severity", "medium").lower())
    except ValueError:
        severity = Severity.MEDIUM

    try:
        issue_type = IssueType(d.get("issue_type", "other").lower())
    except ValueError:
        issue_type = IssueType.OTHER

    return Issue(
        title=d.get("title", "Untitled issue"),
        description=d.get("description", ""),
        file_path=d.get("file_path", ""),
        line_start=d.get("line_start"),
        line_end=d.get("line_end"),
        severity=severity,
        issue_type=issue_type,
        suggestion=d.get("suggestion", ""),
    )


def analyze_chunk(chunk: FileChunk, client: OpenAI, cfg: Config) -> list[Issue]:
    user_content = f"File: {chunk.file_path} (lines {chunk.line_start}-{chunk.line_end})\n\n```\n{chunk.content}\n```"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    response = client.chat.completions.create(
        model=cfg.llm.model,
        max_tokens=cfg.llm.max_tokens,
        messages=messages,
    )
    raw = response.choices[0].message.content or "[]"

    try:
        data = _parse_issues_json(raw)
    except (json.JSONDecodeError, AttributeError):
        correction_messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "Your response was not valid JSON. Please return ONLY a valid JSON array of issues, with no other text."},
        ]
        retry = client.chat.completions.create(
            model=cfg.llm.model,
            max_tokens=cfg.llm.max_tokens,
            messages=correction_messages,
        )
        raw2 = retry.choices[0].message.content or "[]"
        try:
            data = _parse_issues_json(raw2)
        except (json.JSONDecodeError, AttributeError):
            return []

    issues = []
    for d in data:
        if isinstance(d, dict):
            issue = _dict_to_issue(d)
            if issue:
                issues.append(issue)
    return issues


def deduplicate_issues(issues: list[Issue]) -> list[Issue]:
    seen: set[tuple] = set()
    unique = []
    for issue in issues:
        key = (issue.file_path, issue.title.lower()[:60])
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


def analyze_repo(
    repo_path: str,
    cfg: Config,
    memory_store=None,
    progress: Optional[Progress] = None,
) -> IssueReport:
    client = OpenAI(
        api_key=cfg.llm.api_key or "sk-no-key",
        base_url=cfg.llm.base_url,
    )

    all_issues: list[Issue] = []
    files = list(iter_repo_files(repo_path, excluded_dirs=cfg.scan.excluded_dirs))

    task = None
    if progress:
        task = progress.add_task("Scanning files...", total=len(files))

    for file_path in files:
        if progress and task is not None:
            progress.update(task, advance=1, description=f"Scanning {file_path.name}...")

        chunks = list(chunk_file(file_path, chunk_size=cfg.llm.chunk_size))
        for chunk in chunks:
            issues = analyze_chunk(chunk, client, cfg)
            for issue in issues:
                if memory_store and memory_store.is_known_issue(issue, repo_path):
                    continue
                all_issues.append(issue)
                if len(all_issues) >= cfg.scan.max_issues:
                    break
            if len(all_issues) >= cfg.scan.max_issues:
                break
        if len(all_issues) >= cfg.scan.max_issues:
            break

    deduped = deduplicate_issues(all_issues)

    return IssueReport(
        repo_path=repo_path,
        scanned_at=datetime.now(),
        model_used=cfg.llm.model,
        issues=deduped,
    )
