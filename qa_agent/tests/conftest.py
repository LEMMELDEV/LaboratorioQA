"""Fixtures for qa_agent tests: live uvicorn server on a free port + browser session."""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

# Keep the test suite fast: no human-like pacing during pytest.
os.environ["AGENT_PACING"] = "off"

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "apps" / "dummy"))

import pytest  # noqa: E402
import uvicorn  # noqa: E402

from app.defects import DEFECTS, lab_state  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.data import DEFAULT_USER  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    """Live TiendaDemo on a random port for the whole test session."""
    port = _free_port()
    os.environ["BUG_PROFILE"] = "none"
    lab_state.set_profile("none")
    server = uvicorn.Server(uvicorn.Config(
        fastapi_app, host="127.0.0.1", port=port, log_level="warning"
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.1)
    assert server.started, "uvicorn did not start"
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(autouse=True)
def clean_lab_state():
    lab_state.set_profile("none")
    lab_state.disabled.clear()
    yield
    lab_state.set_profile("none")
    lab_state.disabled.clear()


@pytest.fixture
def set_active_bugs():
    def _set(active_ids: set[str]) -> None:
        lab_state.set_profile("default")
        lab_state.disabled = {bid for bid in DEFECTS if bid not in active_ids}
    return _set


@pytest.fixture
def reset_stores():
    from app import data

    yield
    data.ORDERS.clear()
    data.QUOTES.clear()
    data.NEWSLETTER.clear()
    data.USERS.clear()
    data.USERS[DEFAULT_USER["email"]] = dict(DEFAULT_USER)
