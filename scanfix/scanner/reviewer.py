from __future__ import annotations

import json
import re
from dataclasses import dataclass

from openai import OpenAI

from scanfix.models import Issue


SYSTEM_PROMPT = """\
You are a senior software engineer reviewing a list of potential code issues found by an automated scanner.
Your job is to filter out false positives, trivial style nitpicks, and low-value findings.

Keep an issue if it is:
- A genuine bug, security vulnerability, or meaningful performance problem
- Actionable: the suggestion is concrete and the fix is clear
- Not a duplicate of another issue in the list

Reject an issue if it is:
- A false positive or highly speculative
- A trivial style preference with no real impact
- About missing documentation, comments, or metadata (e.g. missing license field)
- About non-code files (e.g. cache files, lock files)

Return ONLY a JSON object with two keys:
- "keep": list of issue IDs to retain
- "rejected": list of objects with "id" and "reason" for each rejected issue

Example:
{
  "keep": ["id1", "id3"],
  "rejected": [
    {"id": "id2", "reason": "False positive: the null check is intentional here"},
    {"id": "id4", "reason": "Trivial style preference with no functional impact"}
  ]
}
No explanation, no markdown, just the JSON object."""


@dataclass
class ReviewResult:
    kept: list[Issue]
    rejected: list[Issue]
    rejection_reasons: dict[str, str]


def _format_issues_for_review(issues: list[Issue]) -> str:
    lines = []
    for issue in issues:
        loc = issue.file_path
        if issue.line_start:
            loc += f":{issue.line_start}"
        lines.append(
            f"ID: {issue.id}\n"
            f"  Title: {issue.title}\n"
            f"  Severity: {issue.severity.value}\n"
            f"  Type: {issue.issue_type.value}\n"
            f"  File: {loc}\n"
            f"  Description: {issue.description}\n"
            f"  Suggestion: {issue.suggestion}"
        )
    return "\n\n".join(lines)


def _parse_response(text: str) -> tuple[list[str] | None, dict[str, str]]:
    text = text.strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
        keep = data.get("keep", [])
        reasons = {
            r["id"]: r.get("reason", "")
            for r in data.get("rejected", [])
            if isinstance(r, dict) and "id" in r
        }
        return keep, reasons
    except (json.JSONDecodeError, AttributeError):
        return None, {}


def review_issues(
    issues: list[Issue],
    client: OpenAI,
    model: str,
    max_tokens: int = 4096,
) -> ReviewResult:
    if not issues:
        return ReviewResult(kept=[], rejected=[], rejection_reasons={})

    user_content = (
        f"Review the following {len(issues)} issues and return keep/rejected with reasons:\n\n"
        + _format_issues_for_review(issues)
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
    )
    raw = response.choices[0].message.content or '{"keep": [], "rejected": []}'

    keep_ids, reasons = _parse_response(raw)

    if keep_ids is None:
        correction_messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": 'Invalid JSON. Return only {"keep": [...], "rejected": [{"id": ..., "reason": ...}]} with no other text.'},
        ]
        retry = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=correction_messages,
        )
        raw2 = retry.choices[0].message.content or '{"keep": [], "rejected": []}'
        keep_ids, reasons = _parse_response(raw2)

    if keep_ids is None:
        return ReviewResult(kept=issues, rejected=[], rejection_reasons={})

    keep_set = set(keep_ids)
    kept = [i for i in issues if i.id in keep_set]
    rejected = [i for i in issues if i.id not in keep_set]

    return ReviewResult(kept=kept, rejected=rejected, rejection_reasons=reasons)
