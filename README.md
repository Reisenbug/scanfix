# Scanfix

AI-powered codebase scanner and fixer. Scans your repo for bugs, security issues, and performance problems using an LLM, optionally fixes them with an AI agent, and outputs reports or GitHub issues/PRs.

## Install

```bash
pip install -e .
```

## Quick Start

```bash
# Initialize config in your repo
scanfix init /path/to/repo

# Scan and report
scanfix scan /path/to/repo

# Scan and auto-fix high+ severity issues
scanfix scan /path/to/repo --fix --severity high
```

## Configuration

Set environment variables (copy `.env.example` to `.env`):

```bash
# Scanner model
SCANFIX_API_KEY=sk-xxx
SCANFIX_BASE_URL=https://api.openai.com/v1
SCANFIX_MODEL=gpt-4o

# Reviewer model (2nd-pass filter, defaults to scanner model if not set)
SCANFIX_REVIEWER_API_KEY=sk-yyy
SCANFIX_REVIEWER_BASE_URL=https://api.openai.com/v1
SCANFIX_REVIEWER_MODEL=gpt-4o-mini

# GitHub integration
GITHUB_TOKEN=ghp-zzz
```

Or configure in `scanfix.toml` at the repo root:

```toml
[llm]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"

[reviewer]
enabled = true
model = "gpt-4o-mini"

[scan]
severity_threshold = "high"
max_issues = 50
excluded_dirs = [".git", "node_modules", "__pycache__", ".venv"]

[output]
output_dir = "./scanfix-output"
github_repo = "owner/repo"
```

Config precedence (high → low): CLI flags > env vars > `scanfix.toml` > `~/.scanfix.toml` > defaults.

## Commands

```bash
scanfix scan [REPO_PATH]         # Scan a repository
scanfix init [REPO_PATH]         # Write default scanfix.toml
scanfix schedule [REPO_PATH]     # Schedule periodic scans via cron
scanfix unschedule [REPO_PATH]   # Remove scheduled scan
scanfix memory stats             # Show memory DB stats
scanfix memory clear             # Clear memory DB
```

### `scan` options

| Flag | Description |
|------|-------------|
| `-m, --model` | Scanner model |
| `-s, --severity` | Min severity: `critical` / `high` / `medium` / `low` |
| `--fix` | Auto-fix issues above threshold |
| `--report-only` | Report only, skip fixing |
| `--github-issues` | Create GitHub issues |
| `--github-prs` | Create GitHub PRs for fixes |
| `--reviewer-model` | Model for 2nd-pass review |
| `--no-review` | Skip 2nd-pass review |

## How It Works

1. **Scan** — walks the repo, chunks files into 150-line segments, sends each to the scanner LLM
2. **Review** — a second LLM pass filters out false positives and low-value findings
3. **Report** — saves JSON + Markdown reports to `./scanfix-output/`
4. **Fix** *(optional)* — runs `mini-swe-agent` on each issue, captures the git diff as a `.patch` file
5. **Memory** — SQLite DB tracks known issues to avoid re-reporting them across runs

## Scheduling

```bash
# Scan every 6 hours
scanfix schedule /path/to/repo --interval 6h

# With auto-fix
scanfix schedule /path/to/repo --interval 24h --fix

# Remove
scanfix unschedule /path/to/repo
```

Writes a crontab entry. Supported intervals: `30m`, `6h`, `1d`, etc.

## Auto-fix

Requires [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent):

```bash
pip install minisweagent
scanfix scan /path/to/repo --fix
```

Each fix is atomic: agent runs → diff captured → saved as `.patch` → git state reset.

## Output

```
scanfix-output/
├── report_20260311_120000.json
├── report_20260311_120000.md
├── <issue-id>.patch          # one per successful fix
```
