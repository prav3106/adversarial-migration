"""
tests/verify/test_run_candidate.py — Tests for verify/run_candidate.py

Covers:
 - Stub module with run() function passes bytes through
 - FileNotFoundError for missing module
 - AttributeError if module lacks run
 - TypeError if run returns non-bytes
"""
from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers: write temp stub modules
# ---------------------------------------------------------------------------

def _write_stub(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_run_candidate_passes_bytes(tmp_path, monkeypatch):
    """A valid stub module with run(record) -> bytes passes through unchanged."""
    stub = _write_stub(tmp_path, "MYPROG.py", """
        from decimal import Decimal

        def run(record):
            return b"0" * 80
    """)
    # Temporarily add to translation/a/ path by monkeypatching
    dest_dir = ROOT / "translation" / "a"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "MYPROG.py"
    dest.write_text(stub.read_text())

    from verify.run_candidate import run_candidate
    try:
        result = run_candidate("MYPROG", "a", {"GP-EMP-ID": "000001"})
        assert isinstance(result, bytes)
        assert result == b"0" * 80
    finally:
        dest.unlink(missing_ok=True)


def test_run_candidate_file_not_found():
    """FileNotFoundError raised when module does not exist."""
    from verify.run_candidate import run_candidate
    with pytest.raises(FileNotFoundError):
        run_candidate("NONEXISTENT_PROG_XYZ", "a", {})


def test_run_candidate_missing_run_function(tmp_path):
    """AttributeError if the module has no run() function."""
    dest_dir = ROOT / "translation" / "a"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "NORUN.py"
    dest.write_text("x = 1\n")

    from verify.run_candidate import run_candidate
    try:
        with pytest.raises(AttributeError):
            run_candidate("NORUN", "a", {})
    finally:
        dest.unlink(missing_ok=True)


def test_run_candidate_non_bytes_return(tmp_path):
    """TypeError if run() returns something other than bytes."""
    dest_dir = ROOT / "translation" / "a"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "RETSTR.py"
    dest.write_text("def run(record):\n    return 'not bytes'\n")

    from verify.run_candidate import run_candidate
    try:
        with pytest.raises(TypeError):
            run_candidate("RETSTR", "a", {})
    finally:
        dest.unlink(missing_ok=True)
