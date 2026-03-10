import tempfile
from pathlib import Path

from scanfix.models import Issue, Severity, IssueType, FixResult
from scanfix.memory.store import MemoryStore


def _make_store(tmp_path: str) -> MemoryStore:
    db = str(Path(tmp_path) / "test.db")
    return MemoryStore(db)


def _make_issue(title: str = "SQL injection vulnerability") -> Issue:
    return Issue(
        title=title,
        description="desc",
        file_path="app.py",
        severity=Severity.HIGH,
        issue_type=IssueType.SECURITY,
        suggestion="use parameterized queries",
    )


def test_save_and_known_issue():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        issue = _make_issue()
        repo = "/tmp/myrepo"

        assert not store.is_known_issue(issue, repo)
        store.save_issue(issue, repo)
        assert store.is_known_issue(issue, repo)
        store.close()


def test_similar_title_detection():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        repo = "/tmp/myrepo"

        original = _make_issue("SQL injection vulnerability")
        store.save_issue(original, repo)

        # Exact same title should be detected as known
        same = _make_issue("SQL injection vulnerability")
        assert store.is_known_issue(same, repo)
        store.close()


def test_mark_fixed():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        repo = "/tmp/myrepo"
        issue = _make_issue()
        store.save_issue(issue, repo)

        result = FixResult(issue=issue, diff="diff --git a/app.py ...", success=True)
        store.mark_fixed(issue.id, result)

        stats = store.get_stats()
        assert stats["fixed_issues"] == 1
        store.close()


def test_stats_empty():
    with tempfile.TemporaryDirectory() as tmp:
        store = _make_store(tmp)
        stats = store.get_stats()
        assert stats["total_issues"] == 0
        assert stats["successful_fixes"] == 0
        store.close()
