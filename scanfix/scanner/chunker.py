from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


CHUNK_SIZE = 150
OVERLAP = 10


@dataclass
class FileChunk:
    file_path: str
    content: str
    line_start: int
    line_end: int
    total_lines: int


def is_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True


def chunk_file(
    path: Path,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = OVERLAP,
) -> Iterator[FileChunk]:
    if is_binary(path):
        return

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return

    total = len(lines)
    if total == 0:
        return

    start = 0
    while start < total:
        end = min(start + chunk_size, total)
        content = "\n".join(lines[start:end])
        yield FileChunk(
            file_path=str(path),
            content=content,
            line_start=start + 1,
            line_end=end,
            total_lines=total,
        )
        if end >= total:
            break
        start = end - overlap
