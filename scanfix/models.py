from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueType(str, Enum):
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    OTHER = "other"


SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


@dataclass
class Issue:
    title: str
    description: str
    file_path: str
    severity: Severity
    issue_type: IssueType
    suggestion: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def severity_value(self) -> int:
        return SEVERITY_ORDER.get(self.severity, 99)


@dataclass
class IssueReport:
    repo_path: str
    scanned_at: datetime
    model_used: str
    issues: list[Issue] = field(default_factory=list)

    def filter_by_severity(self, min_severity: Severity) -> list[Issue]:
        threshold = SEVERITY_ORDER[min_severity]
        return [i for i in self.issues if SEVERITY_ORDER.get(i.severity, 99) <= threshold]


@dataclass
class FixResult:
    issue: Issue
    diff: str
    success: bool
    error_message: Optional[str] = None
    github_issue_url: Optional[str] = None
    github_pr_url: Optional[str] = None
