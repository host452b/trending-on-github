"""Smoke tests for build_markdown.py.

build_markdown.py lives at the repo root (not inside the trending
package), so we import it via importlib.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def md_mod():
    path = REPO_ROOT / "build_markdown.py"
    spec = importlib.util.spec_from_file_location("build_markdown", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_escape_pipe_replaces_only_pipes(md_mod):
    assert md_mod.escape_pipe("a|b|c") == "a\\|b\\|c"
    assert md_mod.escape_pipe("nothing-special") == "nothing-special"
    assert md_mod.escape_pipe("") == ""
    # None passes through as empty string
    assert md_mod.escape_pipe(None) == ""


def test_escape_pipe_is_idempotent(md_mod):
    once = md_mod.escape_pipe("a|b")
    twice = md_mod.escape_pipe(once)
    assert twice == once == "a\\|b"


def test_format_int_groups_thousands(md_mod):
    assert md_mod.format_int(1234) == "1,234"
    assert md_mod.format_int(0) == "0"
    assert md_mod.format_int(1_000_000) == "1,000,000"
