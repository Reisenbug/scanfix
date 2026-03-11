from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


load_dotenv()


@dataclass
class LLMConfig:
    model: str = "claude-3-5-sonnet-20241022"
    base_url: str = "https://api.anthropic.com/v1"
    api_key: str = ""
    max_tokens: int = 4096
    chunk_size: int = 150


@dataclass
class ScanConfig:
    severity_threshold: str = "high"
    max_issues: int = 50
    excluded_dirs: list[str] = field(
        default_factory=lambda: [".git", "node_modules", "__pycache__", ".venv", "venv"]
    )


@dataclass
class OutputConfig:
    output_dir: str = "./scanfix-output"
    create_github_issues: bool = False
    create_github_prs: bool = False
    github_repo: str = ""


@dataclass
class MemoryConfig:
    db_path: str = "~/.scanfix/memory.db"


@dataclass
class ReviewerConfig:
    enabled: bool = True
    model: str = ""
    base_url: str = ""
    api_key: str = ""


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    reviewer: ReviewerConfig = field(default_factory=ReviewerConfig)
    scan: ScanConfig = field(default_factory=ScanConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    github_token: str = ""


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _merge_llm(cfg: LLMConfig, data: dict) -> None:
    llm = data.get("llm", {})
    if "model" in llm:
        cfg.model = llm["model"]
    if "base_url" in llm:
        cfg.base_url = llm["base_url"]
    if "api_key" in llm:
        cfg.api_key = llm["api_key"]
    if "max_tokens" in llm:
        cfg.max_tokens = llm["max_tokens"]
    if "chunk_size" in llm:
        cfg.chunk_size = llm["chunk_size"]


def _merge_scan(cfg: ScanConfig, data: dict) -> None:
    scan = data.get("scan", {})
    if "severity_threshold" in scan:
        cfg.severity_threshold = scan["severity_threshold"]
    if "max_issues" in scan:
        cfg.max_issues = scan["max_issues"]
    if "excluded_dirs" in scan:
        cfg.excluded_dirs = scan["excluded_dirs"]


def _merge_output(cfg: OutputConfig, data: dict) -> None:
    out = data.get("output", {})
    if "output_dir" in out:
        cfg.output_dir = out["output_dir"]
    if "create_github_issues" in out:
        cfg.create_github_issues = out["create_github_issues"]
    if "create_github_prs" in out:
        cfg.create_github_prs = out["create_github_prs"]
    if "github_repo" in out:
        cfg.github_repo = out["github_repo"]


def _merge_reviewer(cfg: ReviewerConfig, data: dict) -> None:
    rev = data.get("reviewer", {})
    if "enabled" in rev:
        cfg.enabled = rev["enabled"]
    if "model" in rev:
        cfg.model = rev["model"]
    if "base_url" in rev:
        cfg.base_url = rev["base_url"]
    if "api_key" in rev:
        cfg.api_key = rev["api_key"]


def _merge_memory(cfg: MemoryConfig, data: dict) -> None:
    mem = data.get("memory", {})
    if "db_path" in mem:
        cfg.db_path = mem["db_path"]


def load_config(
    repo_path: Optional[str] = None,
    model: Optional[str] = None,
    severity: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    output_dir: Optional[str] = None,
    github_issues: Optional[bool] = None,
    github_prs: Optional[bool] = None,
    github_repo: Optional[str] = None,
    reviewer_model: Optional[str] = None,
    reviewer_base_url: Optional[str] = None,
    reviewer_api_key: Optional[str] = None,
    no_review: bool = False,
) -> Config:
    cfg = Config()

    global_toml = _load_toml(Path.home() / ".scanfix.toml")
    _merge_llm(cfg.llm, global_toml)
    _merge_reviewer(cfg.reviewer, global_toml)
    _merge_scan(cfg.scan, global_toml)
    _merge_output(cfg.output, global_toml)
    _merge_memory(cfg.memory, global_toml)

    if repo_path:
        repo_toml = _load_toml(Path(repo_path) / "scanfix.toml")
        _merge_llm(cfg.llm, repo_toml)
        _merge_reviewer(cfg.reviewer, repo_toml)
        _merge_scan(cfg.scan, repo_toml)
        _merge_output(cfg.output, repo_toml)
        _merge_memory(cfg.memory, repo_toml)

    env_api_key = os.environ.get("SCANFIX_API_KEY", "")
    if env_api_key:
        cfg.llm.api_key = env_api_key

    env_base_url = os.environ.get("SCANFIX_BASE_URL", "")
    if env_base_url:
        cfg.llm.base_url = env_base_url

    env_model = os.environ.get("SCANFIX_MODEL", "")
    if env_model:
        cfg.llm.model = env_model

    env_rev_api_key = os.environ.get("SCANFIX_REVIEWER_API_KEY", "")
    if env_rev_api_key:
        cfg.reviewer.api_key = env_rev_api_key

    env_rev_base_url = os.environ.get("SCANFIX_REVIEWER_BASE_URL", "")
    if env_rev_base_url:
        cfg.reviewer.base_url = env_rev_base_url

    env_rev_model = os.environ.get("SCANFIX_REVIEWER_MODEL", "")
    if env_rev_model:
        cfg.reviewer.model = env_rev_model

    cfg.github_token = os.environ.get("GITHUB_TOKEN", "")

    if model:
        cfg.llm.model = model
    if severity:
        cfg.scan.severity_threshold = severity
    if base_url:
        cfg.llm.base_url = base_url
    if api_key:
        cfg.llm.api_key = api_key
    if output_dir:
        cfg.output.output_dir = output_dir
    if github_issues is not None:
        cfg.output.create_github_issues = github_issues
    if github_prs is not None:
        cfg.output.create_github_prs = github_prs
    if github_repo:
        cfg.output.github_repo = github_repo
    if reviewer_model:
        cfg.reviewer.model = reviewer_model
    if reviewer_base_url:
        cfg.reviewer.base_url = reviewer_base_url
    if reviewer_api_key:
        cfg.reviewer.api_key = reviewer_api_key
    if no_review:
        cfg.reviewer.enabled = False

    return cfg


DEFAULT_TOML = """\
[llm]
model = "claude-3-5-sonnet-20241022"
base_url = "https://api.anthropic.com/v1"
max_tokens = 4096
chunk_size = 150

[reviewer]
enabled = true
# model defaults to [llm] model if not set
# model = "gpt-4o-mini"
# base_url = "https://api.openai.com/v1"

[scan]
severity_threshold = "high"
max_issues = 50
excluded_dirs = [".git", "node_modules", "__pycache__", ".venv"]

[output]
output_dir = "./scanfix-output"
create_github_issues = false
create_github_prs = false
github_repo = "owner/repo"

[memory]
db_path = "~/.scanfix/memory.db"
"""
