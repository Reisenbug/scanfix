from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from scanfix.models import FixResult, IssueReport, Severity

console = Console()

SEVERITY_COLORS = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "blue",
}


def print_scan_summary(report: IssueReport, fix_results: Optional[list[FixResult]] = None) -> None:
    counts = {s: 0 for s in Severity}
    for issue in report.issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1

    console.print()
    console.print(Panel(
        f"[bold]Scan complete[/bold]\n"
        f"Repo: {report.repo_path}\n"
        f"Model: {report.model_used}\n"
        f"Time: {report.scanned_at.strftime('%Y-%m-%d %H:%M:%S')}",
        title="[bold cyan]Scanfix Report[/bold cyan]",
        box=box.ROUNDED,
    ))

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Severity", style="bold")
    table.add_column("Count", justify="right")
    for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
        color = SEVERITY_COLORS[sev]
        table.add_row(f"[{color}]{sev.value.upper()}[/{color}]", str(counts[sev]))
    table.add_row("[bold]TOTAL[/bold]", str(len(report.issues)), style="bold")
    console.print(table)

    if not report.issues:
        console.print("[green]No issues found![/green]")
        return

    issues_table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
    issues_table.add_column("#", width=4, justify="right")
    issues_table.add_column("Severity", width=10)
    issues_table.add_column("Type", width=12)
    issues_table.add_column("File", max_width=40, no_wrap=True)
    issues_table.add_column("Title", max_width=50)

    for i, issue in enumerate(report.issues, 1):
        color = SEVERITY_COLORS.get(issue.severity, "white")
        location = Path(issue.file_path).name
        if issue.line_start:
            location += f":{issue.line_start}"
        issues_table.add_row(
            str(i),
            f"[{color}]{issue.severity.value}[/{color}]",
            issue.issue_type.value,
            location,
            issue.title,
        )

    console.print(issues_table)

    if fix_results:
        fixed = sum(1 for r in fix_results if r.success)
        console.print(f"\n[bold]Fixes applied:[/bold] {fixed}/{len(fix_results)} successful")


def save_report_json(report: IssueReport, output_dir: str) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    timestamp = report.scanned_at.strftime("%Y%m%d_%H%M%S")
    path = out / f"report_{timestamp}.json"

    data = {
        "repo_path": report.repo_path,
        "scanned_at": report.scanned_at.isoformat(),
        "model_used": report.model_used,
        "total_issues": len(report.issues),
        "issues": [
            {
                "id": issue.id,
                "title": issue.title,
                "description": issue.description,
                "file_path": issue.file_path,
                "line_start": issue.line_start,
                "line_end": issue.line_end,
                "severity": issue.severity.value,
                "issue_type": issue.issue_type.value,
                "suggestion": issue.suggestion,
            }
            for issue in report.issues
        ],
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def save_report_markdown(report: IssueReport, output_dir: str) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    timestamp = report.scanned_at.strftime("%Y%m%d_%H%M%S")
    path = out / f"report_{timestamp}.md"

    lines = [
        f"# Scanfix Report",
        f"",
        f"- **Repo:** {report.repo_path}",
        f"- **Scanned:** {report.scanned_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Model:** {report.model_used}",
        f"- **Total Issues:** {len(report.issues)}",
        f"",
    ]

    by_severity: dict = {}
    for issue in report.issues:
        by_severity.setdefault(issue.severity, []).append(issue)

    for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
        issues = by_severity.get(sev, [])
        if not issues:
            continue
        lines.append(f"## {sev.value.upper()} ({len(issues)})")
        lines.append("")
        for issue in issues:
            loc = issue.file_path
            if issue.line_start:
                loc += f":{issue.line_start}"
            lines.append(f"### {issue.title}")
            lines.append(f"- **File:** `{loc}`")
            lines.append(f"- **Type:** {issue.issue_type.value}")
            lines.append(f"")
            lines.append(f"{issue.description}")
            lines.append(f"")
            lines.append(f"**Suggestion:** {issue.suggestion}")
            lines.append(f"")

    path.write_text("\n".join(lines))
    return path
