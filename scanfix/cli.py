from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich import box

from scanfix.config import DEFAULT_TOML, load_config
from scanfix.models import Severity

console = Console()


@click.group()
@click.version_option()
def cli():
    """Scanfix - AI-powered codebase scanner and fixer."""


@cli.command()
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--model", "-m", help="LLM model to use")
@click.option("--severity", "-s", default=None, help="Minimum severity threshold (critical/high/medium/low)")
@click.option("--fix/--no-fix", default=False, help="Attempt to fix discovered issues")
@click.option("--github-issues", is_flag=True, default=False, help="Create GitHub issues for findings")
@click.option("--github-prs", is_flag=True, default=False, help="Create GitHub PRs for fixes")
@click.option("--report-only", is_flag=True, default=False, help="Only generate report, skip fixing")
@click.option("--output-dir", "-o", default=None, help="Output directory for reports and patches")
@click.option("--github-repo", default=None, help="GitHub repo (owner/repo)")
@click.option("--api-key", envvar="SCANFIX_API_KEY", default=None, help="API key")
@click.option("--base-url", envvar="SCANFIX_BASE_URL", default=None, help="LLM API base URL")
@click.option("--reviewer-model", default=None, help="Model for 2nd-pass review (defaults to scanner model)")
@click.option("--reviewer-base-url", envvar="SCANFIX_REVIEWER_BASE_URL", default=None, help="Base URL for reviewer model")
@click.option("--reviewer-api-key", envvar="SCANFIX_REVIEWER_API_KEY", default=None, help="API key for reviewer model")
@click.option("--no-review", is_flag=True, default=False, help="Skip 2nd-pass review filter")
def scan(
    repo_path,
    model,
    severity,
    fix,
    github_issues,
    github_prs,
    report_only,
    output_dir,
    github_repo,
    api_key,
    base_url,
    reviewer_model,
    reviewer_base_url,
    reviewer_api_key,
    no_review,
):
    """Scan a repository for issues using AI."""
    from scanfix.config import load_config
    from scanfix.scanner.analyzer import analyze_repo
    from scanfix.output.reporter import print_scan_summary, save_report_json, save_report_markdown
    from scanfix.memory.store import MemoryStore

    cfg = load_config(
        repo_path=repo_path,
        model=model,
        severity=severity,
        base_url=base_url,
        api_key=api_key,
        output_dir=output_dir,
        github_issues=github_issues if github_issues else None,
        github_prs=github_prs if github_prs else None,
        github_repo=github_repo,
        reviewer_model=reviewer_model,
        reviewer_base_url=reviewer_base_url,
        reviewer_api_key=reviewer_api_key,
        no_review=no_review,
    )

    if not cfg.llm.api_key:
        console.print("[red]Error:[/red] No API key configured. Set SCANFIX_API_KEY or use --api-key.")
        sys.exit(1)

    memory_store = MemoryStore(cfg.memory.db_path)

    console.print(f"[bold cyan]Scanning[/bold cyan] {repo_path} with model [bold]{cfg.llm.model}[/bold]...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        report = analyze_repo(repo_path, cfg, memory_store=memory_store, progress=progress)

    if cfg.reviewer.enabled and report.issues:
        from scanfix.scanner.reviewer import review_issues
        from openai import OpenAI

        rev_model = cfg.reviewer.model or cfg.llm.model
        rev_base_url = cfg.reviewer.base_url or cfg.llm.base_url
        rev_api_key = cfg.reviewer.api_key or cfg.llm.api_key

        console.print(
            f"[bold cyan]Reviewing[/bold cyan] {len(report.issues)} issues "
            f"with model [bold]{rev_model}[/bold]..."
        )
        rev_client = OpenAI(api_key=rev_api_key or "sk-no-key", base_url=rev_base_url)
        result = review_issues(report.issues, rev_client, rev_model, cfg.llm.max_tokens)
        before = len(report.issues)
        after = len(result.kept)
        console.print(f"  [dim]Filtered {before - after} false positives, {after} issues remaining.[/dim]")

        if result.rejected:
            from rich.table import Table
            from rich import box as rich_box
            t = Table(box=rich_box.SIMPLE, show_header=True, header_style="bold")
            t.add_column("Rejected Issue", max_width=40)
            t.add_column("Reason", max_width=60)
            for issue in result.rejected:
                reason = result.rejection_reasons.get(issue.id, "—")
                t.add_row(f"[dim]{issue.title}[/dim]", f"[dim]{reason}[/dim]")
            console.print(t)

        report.issues = result.kept

    for issue in report.issues:
        memory_store.save_issue(issue, repo_path)

    json_path = save_report_json(report, cfg.output.output_dir)
    md_path = save_report_markdown(report, cfg.output.output_dir)
    console.print(f"Reports saved to [dim]{json_path}[/dim] and [dim]{md_path}[/dim]")

    fix_results = []
    if not report_only and (fix or cfg.output.create_github_prs):
        threshold = Severity(cfg.scan.severity_threshold)
        actionable = report.filter_by_severity(threshold)
        if actionable:
            console.print(f"\n[bold]Fixing {len(actionable)} issues...[/bold]")
            from scanfix.agent.fixer import fix_issues
            fix_results = fix_issues(actionable, repo_path, cfg.output.output_dir, memory_store)
        else:
            console.print("[dim]No issues above threshold to fix.[/dim]")

    if cfg.output.create_github_issues or github_issues:
        if not cfg.github_token:
            console.print("[yellow]Warning:[/yellow] GITHUB_TOKEN not set, skipping GitHub issues.")
        elif not cfg.output.github_repo:
            console.print("[yellow]Warning:[/yellow] No github_repo configured, skipping GitHub issues.")
        else:
            from scanfix.output.github import create_github_issue
            threshold = Severity(cfg.scan.severity_threshold)
            actionable = report.filter_by_severity(threshold)
            for issue in actionable:
                url = create_github_issue(issue, cfg.output.github_repo, cfg.github_token)
                if url:
                    console.print(f"  GitHub issue: {url}")

    if fix_results and (cfg.output.create_github_prs or github_prs):
        if not cfg.github_token:
            console.print("[yellow]Warning:[/yellow] GITHUB_TOKEN not set, skipping GitHub PRs.")
        elif not cfg.output.github_repo:
            console.print("[yellow]Warning:[/yellow] No github_repo configured, skipping GitHub PRs.")
        else:
            from scanfix.output.github import create_github_pr
            for result in fix_results:
                if result.success:
                    url = create_github_pr(result, cfg.output.github_repo, cfg.github_token, repo_path)
                    if url:
                        console.print(f"  GitHub PR: {url}")

    print_scan_summary(report, fix_results if fix_results else None)
    memory_store.close()


@cli.command()
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--interval", "-i", default="24h", help="Scan interval (e.g. 6h, 30m, 1d)")
@click.option("--severity", "-s", default=None, help="Severity threshold for scheduled scans")
@click.option("--fix/--no-fix", default=False, help="Auto-fix during scheduled scans")
def schedule(repo_path, interval, severity, fix):
    """Schedule periodic scans using cron."""
    minutes = _parse_interval(interval)
    if minutes is None:
        console.print(f"[red]Invalid interval:[/red] {interval}. Use format like 6h, 30m, 1d.")
        sys.exit(1)

    scanfix_bin = _find_scanfix_bin()
    repo_abs = str(Path(repo_path).resolve())

    fix_flag = "--fix" if fix else ""
    sev_flag = f"--severity {severity}" if severity else ""
    cmd_parts = [p for p in [scanfix_bin, "scan", repo_abs, sev_flag, fix_flag] if p]
    cmd = " ".join(cmd_parts)

    cron_expr = _minutes_to_cron(minutes)
    cron_line = f"{cron_expr} {cmd}  # scanfix:{repo_abs}"

    existing = _get_crontab()
    tag = f"# scanfix:{repo_abs}"
    filtered = [line for line in existing.splitlines() if tag not in line]
    filtered.append(cron_line)
    new_crontab = "\n".join(filtered) + "\n"
    _set_crontab(new_crontab)

    console.print(f"[green]Scheduled[/green] scan of {repo_abs} every {interval}")
    console.print(f"  Cron: [dim]{cron_expr}[/dim]")


@cli.command()
@click.argument("repo_path", default=".", type=click.Path())
def unschedule(repo_path):
    """Remove scheduled scan for a repository."""
    repo_abs = str(Path(repo_path).resolve())
    tag = f"# scanfix:{repo_abs}"
    existing = _get_crontab()
    filtered = [line for line in existing.splitlines() if tag not in line]
    new_crontab = "\n".join(filtered) + "\n"
    _set_crontab(new_crontab)
    console.print(f"[green]Unscheduled[/green] scan for {repo_abs}")


@cli.command("init")
@click.argument("repo_path", default=".", type=click.Path(exists=True, file_okay=False))
def init_cmd(repo_path):
    """Write default scanfix.toml to a repository."""
    dest = Path(repo_path) / "scanfix.toml"
    if dest.exists():
        if not click.confirm(f"{dest} already exists. Overwrite?"):
            console.print("Aborted.")
            return
    dest.write_text(DEFAULT_TOML)
    console.print(f"[green]Created[/green] {dest}")


@cli.group("memory")
def memory_group():
    """Manage the issue memory database."""


@memory_group.command("stats")
@click.option("--db-path", default=None, help="Path to memory DB")
def memory_stats(db_path):
    """Show memory database statistics."""
    from scanfix.memory.store import MemoryStore
    cfg = load_config()
    store = MemoryStore(db_path or cfg.memory.db_path)
    stats = store.get_stats()
    store.close()

    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    for k, v in stats.items():
        table.add_row(k.replace("_", " ").title(), str(v))
    console.print(table)


@memory_group.command("clear")
@click.option("--db-path", default=None, help="Path to memory DB")
@click.confirmation_option(prompt="This will delete all stored issues and fixes. Continue?")
def memory_clear(db_path):
    """Clear all stored issues and fixes."""
    from scanfix.memory.store import MemoryStore
    cfg = load_config()
    store = MemoryStore(db_path or cfg.memory.db_path)
    store.clear()
    store.close()
    console.print("[green]Memory cleared.[/green]")


def _parse_interval(interval: str) -> int | None:
    match = re.fullmatch(r"(\d+)(m|h|d)", interval.strip().lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == "m":
        return value
    if unit == "h":
        return value * 60
    if unit == "d":
        return value * 60 * 24
    return None


def _minutes_to_cron(minutes: int) -> str:
    if minutes < 60:
        return f"*/{minutes} * * * *"
    hours = minutes // 60
    if hours < 24:
        return f"0 */{hours} * * *"
    days = hours // 24
    return f"0 0 */{days} * *"


def _find_scanfix_bin() -> str:
    import shutil
    found = shutil.which("scanfix")
    if found:
        return found
    return sys.executable + " -m scanfix"


def _get_crontab() -> str:
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return result.stdout


def _set_crontab(content: str) -> None:
    proc = subprocess.run(["crontab", "-"], input=content, capture_output=True, text=True)
    if proc.returncode != 0:
        console.print(f"[red]Failed to update crontab:[/red] {proc.stderr}")
        sys.exit(1)
