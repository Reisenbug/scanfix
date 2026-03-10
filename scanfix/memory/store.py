from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from scanfix.models import FixResult, Issue


def _title_similarity(a: str, b: str) -> float:
    a_words = set(a.lower().split())
    b_words = set(b.lower().split())
    if not a_words or not b_words:
        return 0.0
    intersection = len(a_words & b_words)
    union = len(a_words | b_words)
    return intersection / union


class MemoryStore:
    def __init__(self, db_path: str = "~/.scanfix/memory.db") -> None:
        resolved = Path(db_path).expanduser()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(resolved))
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS issues (
                id TEXT PRIMARY KEY,
                repo TEXT NOT NULL,
                file_path TEXT NOT NULL,
                title TEXT NOT NULL,
                severity TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fixes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id TEXT NOT NULL,
                diff TEXT,
                success INTEGER NOT NULL,
                error_message TEXT,
                agent_context_used TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (issue_id) REFERENCES issues(id)
            );
        """)
        self.conn.commit()

    def save_issue(self, issue: Issue, repo_path: str) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO issues
                (id, repo, file_path, title, severity, issue_type, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                issue.id,
                repo_path,
                issue.file_path,
                issue.title,
                issue.severity.value,
                issue.issue_type.value,
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def is_known_issue(self, issue: Issue, repo_path: str, threshold: float = 0.85) -> bool:
        rows = self.conn.execute(
            "SELECT title FROM issues WHERE repo = ? AND file_path = ?",
            (repo_path, issue.file_path),
        ).fetchall()
        for (existing_title,) in rows:
            if _title_similarity(issue.title, existing_title) >= threshold:
                return True
        return False

    def mark_fixed(self, issue_id: str, fix_result: FixResult, agent_context: str = "") -> None:
        self.conn.execute(
            "UPDATE issues SET status = 'fixed' WHERE id = ?",
            (issue_id,),
        )
        self.conn.execute(
            """
            INSERT INTO fixes (issue_id, diff, success, error_message, agent_context_used, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                issue_id,
                fix_result.diff,
                int(fix_result.success),
                fix_result.error_message,
                agent_context,
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def get_fix_history(self, repo_path: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT i.title, i.severity, i.issue_type, i.file_path,
                   f.diff, f.success, f.created_at
            FROM fixes f
            JOIN issues i ON f.issue_id = i.id
            WHERE i.repo = ?
            ORDER BY f.created_at DESC
            LIMIT ?
            """,
            (repo_path, limit),
        ).fetchall()
        return [
            {
                "title": r[0],
                "severity": r[1],
                "issue_type": r[2],
                "file_path": r[3],
                "diff": r[4],
                "success": bool(r[5]),
                "created_at": r[6],
            }
            for r in rows
        ]

    def get_similar_fixes(self, issue: Issue, limit: int = 5) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT i.title, i.issue_type, f.diff, f.created_at
            FROM fixes f
            JOIN issues i ON f.issue_id = i.id
            WHERE i.issue_type = ? AND f.success = 1
            ORDER BY f.created_at DESC
            LIMIT ?
            """,
            (issue.issue_type.value, limit),
        ).fetchall()
        return [
            {
                "title": r[0],
                "issue_type": r[1],
                "diff": r[2],
                "created_at": r[3],
            }
            for r in rows
        ]

    def get_stats(self) -> dict:
        total_issues = self.conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0]
        fixed_issues = self.conn.execute("SELECT COUNT(*) FROM issues WHERE status = 'fixed'").fetchone()[0]
        total_fixes = self.conn.execute("SELECT COUNT(*) FROM fixes").fetchone()[0]
        successful_fixes = self.conn.execute("SELECT COUNT(*) FROM fixes WHERE success = 1").fetchone()[0]
        return {
            "total_issues": total_issues,
            "fixed_issues": fixed_issues,
            "open_issues": total_issues - fixed_issues,
            "total_fix_attempts": total_fixes,
            "successful_fixes": successful_fixes,
        }

    def clear(self) -> None:
        self.conn.executescript("DELETE FROM fixes; DELETE FROM issues;")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
