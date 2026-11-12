"""Human-like pacing between browser actions.

Controlled by env vars (read at call time so runs can be tuned live):
- AGENT_PACING           on | off     (default: on)
- AGENT_STEP_DELAY_MS    base pause after each action (default: 800)
- AGENT_JITTER_MS        random extra pause 0..N (default: 400)
- AGENT_REVIEW_DELAY_MS  long "look at the result" pause at criterion close
                         (default: 2000)

Presets:
- action    -> step_delay + jitter           (every click / fill / select)
- navigate  -> step_delay*1.5 + jitter       (arrival at a new screen, reading)
- review    -> review_delay + jitter         (criterion close, before evidence)

The test suite forces AGENT_PACING=off in conftest so pytest stays fast.
"""
from __future__ import annotations

import os
import random
import time

_PRESETS: dict[str, tuple[str, float]] = {
    "action": ("AGENT_STEP_DELAY_MS", 1.0),
    "navigate": ("AGENT_STEP_DELAY_MS", 1.5),
    "review": ("AGENT_REVIEW_DELAY_MS", 1.0),
}

_DEFAULTS = {"AGENT_STEP_DELAY_MS": 800, "AGENT_JITTER_MS": 400, "AGENT_REVIEW_DELAY_MS": 2000}


def pacing_enabled() -> bool:
    return os.environ.get("AGENT_PACING", "on").strip().lower() not in ("off", "0", "false", "no")


def _env_int(name: str) -> int:
    try:
        return int(os.environ.get(name, _DEFAULTS[name]))
    except (ValueError, KeyError):
        return _DEFAULTS.get(name, 0)


def human_pause(kind: str = "action") -> None:
    """Sleep base + jitter to make the run observable (like a human tester)."""
    if not pacing_enabled():
        return
    env_name, factor = _PRESETS.get(kind, _PRESETS["action"])
    base = int(_env_int(env_name) * factor)
    jitter = _env_int("AGENT_JITTER_MS")
    delay = max(0, base + random.randint(0, max(0, jitter)))
    if delay:
        time.sleep(delay / 1000.0)


def configured_delays() -> dict:
    return {
        "pacing": "on" if pacing_enabled() else "off",
        "step_delay_ms": _env_int("AGENT_STEP_DELAY_MS"),
        "jitter_ms": _env_int("AGENT_JITTER_MS"),
        "review_delay_ms": _env_int("AGENT_REVIEW_DELAY_MS"),
    }
