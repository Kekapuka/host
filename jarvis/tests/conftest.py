import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def jarvis_home(tmp_path, monkeypatch):
    """Every test gets its own data folder."""
    home = tmp_path / "jarvis-home"
    monkeypatch.setenv("JARVIS_HOME", str(home))
    return home


@pytest.fixture
def store(jarvis_home):
    from jarvis import paths
    from jarvis.store import CommandStore

    s = CommandStore(paths.commands_dir())
    s.ensure_seeded("ru")
    return s


def pytest_configure(config):
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
