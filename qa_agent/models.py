"""Core dataclasses for the QA run (Temporal payloads are plain dicts)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"


@dataclass
class Scenario:
    id: str
    name: str
    feature: str
    tags: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)


@dataclass
class TestCase:
    case_id: str            # e.g. "criterio-cart-02"
    scenario_id: str
    name: str
    feature: str
    checks: list[dict] = field(default_factory=list)  # [{"check": id, "args": {...}}]
    interpretation: Optional[dict] = None             # Interpretation.to_dict()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TestCase":
        return cls(**d)


@dataclass
class CheckResult:
    check: str
    status: str             # PASS | FAIL | BLOCKED
    detail: str = ""
    observed: str = ""
    expected: str = ""
    evidence: list[str] = field(default_factory=list)   # relative paths
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CaseResult:
    case_id: str
    scenario_id: str
    name: str
    feature: str
    status: str
    results: list[CheckResult] = field(default_factory=list)
    error: Optional[str] = None
    interpretation: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CaseResult":
        results = [CheckResult(**r) for r in d.pop("results", [])]
        return cls(**d, results=results)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
