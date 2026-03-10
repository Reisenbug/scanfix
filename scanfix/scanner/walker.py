from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Optional

import pathspec


def load_gitignore_spec(repo_path: Path) -> Optional[pathspec.PathSpec]:
    gitignore = repo_path / ".gitignore"
    if not gitignore.exists():
        return None
    patterns = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def iter_repo_files(
    repo_path: str,
    excluded_dirs: list[str] | None = None,
) -> Iterator[Path]:
    root = Path(repo_path).resolve()
    excluded = set(excluded_dirs or [".git", "node_modules", "__pycache__", ".venv", "venv"])
    spec = load_gitignore_spec(root)

    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel_dir = current.relative_to(root)

        dirnames[:] = [
            d for d in dirnames
            if d not in excluded
            and not (spec and spec.match_file(str(rel_dir / d) + "/"))
        ]

        for filename in filenames:
            file_path = current / filename
            rel_path = file_path.relative_to(root)
            if spec and spec.match_file(str(rel_path)):
                continue
            yield file_path
