import tempfile
from pathlib import Path

from scanfix.scanner.chunker import chunk_file, is_binary
from scanfix.scanner.walker import iter_repo_files


def test_is_binary_text_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("print('hello')\n")
        p = Path(f.name)
    assert not is_binary(p)
    p.unlink()


def test_is_binary_binary_file():
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".bin", delete=False) as f:
        f.write(b"\x00\x01\x02hello")
        p = Path(f.name)
    assert is_binary(p)
    p.unlink()


def test_chunk_file_small():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        lines = [f"line {i}" for i in range(10)]
        f.write("\n".join(lines))
        p = Path(f.name)
    chunks = list(chunk_file(p, chunk_size=150))
    assert len(chunks) == 1
    assert chunks[0].line_start == 1
    assert chunks[0].line_end == 10
    p.unlink()


def test_chunk_file_overlap():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        lines = [f"line {i}" for i in range(30)]
        f.write("\n".join(lines))
        p = Path(f.name)
    chunks = list(chunk_file(p, chunk_size=20, overlap=5))
    assert len(chunks) > 1
    assert chunks[1].line_start == chunks[0].line_end - 5 + 1
    p.unlink()


def test_iter_repo_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text("print('hi')")
        (root / "node_modules").mkdir()
        (root / "node_modules" / "pkg.js").write_text("module.exports = {}")

        files = list(iter_repo_files(tmpdir, excluded_dirs=["node_modules"]))
        names = [f.name for f in files]
        assert "main.py" in names
        assert "pkg.js" not in names
