"""Pytest fixtures for TiendaDemo.

Run from apps/dummy:  ``python -m pytest tests -q``
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.defects import DEFECTS, lab_state  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    """Clean-app client (no bugs). Resets the lab state after each test."""
    lab_state.set_profile("none")
    lab_state.disabled.clear()
    with TestClient(app, follow_redirects=False) as c:
        yield c
    lab_state.set_profile("none")
    lab_state.disabled.clear()


@pytest.fixture(autouse=True)
def reset_stores():
    """Isolate in-memory stores between tests (they are module-level globals)."""
    from app import data
    from app.data import DEFAULT_USER

    yield
    data.ORDERS.clear()
    data.QUOTES.clear()
    data.NEWSLETTER.clear()
    data.USERS.clear()
    data.USERS[DEFAULT_USER["email"]] = dict(DEFAULT_USER)


def set_active_bugs(active_ids: set[str]) -> None:
    """Enable exactly the given defects (others disabled)."""
    lab_state.set_profile("default")
    lab_state.disabled = {bid for bid in DEFECTS if bid not in active_ids}


@pytest.fixture
def with_bugs():
    """Usage: with_bugs({'BUG-02'}) -> callable enabling those bugs; state reset by client fixture."""

    def _enable(ids: set[str]) -> None:
        set_active_bugs(ids)

    return _enable
