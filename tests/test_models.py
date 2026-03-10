from scanfix.models import Issue, IssueReport, Severity, IssueType
from datetime import datetime


def _make_issue(severity: Severity) -> Issue:
    return Issue(
        title="Test issue",
        description="desc",
        file_path="foo.py",
        severity=severity,
        issue_type=IssueType.BUG,
        suggestion="fix it",
    )


def test_filter_by_severity():
    report = IssueReport(
        repo_path="/tmp",
        scanned_at=datetime.now(),
        model_used="test",
        issues=[
            _make_issue(Severity.CRITICAL),
            _make_issue(Severity.HIGH),
            _make_issue(Severity.MEDIUM),
            _make_issue(Severity.LOW),
        ],
    )
    high_plus = report.filter_by_severity(Severity.HIGH)
    assert len(high_plus) == 2

    critical_only = report.filter_by_severity(Severity.CRITICAL)
    assert len(critical_only) == 1


def test_issue_has_id():
    issue = _make_issue(Severity.LOW)
    assert issue.id
    assert len(issue.id) > 0
