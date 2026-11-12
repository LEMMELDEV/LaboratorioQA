"""Interpretation layer: how the agent UNDERSTOOD each acceptance criterion.

One Interpretation per criterion, produced BEFORE execution (by the heuristic
interpreter today, by the LLM planner in M4 — same contract either way) and
shown to the human reviewer at the HITL gate, in plan.md and in summary.md.

Honesty rule: `unknowns` must list what could not be resolved instead of
inventing details; `assertion.origin` states where the expected value comes
from (criterion text, computed formula, or app display).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class InterpStep:
    order: int
    action: str          # goto | fill | select | click | submit | assert
    target: str          # pantalla o elemento descriptivo
    detail: str = ""     # valor u observación adicional


@dataclass
class InterpAssertion:
    what: str            # qué se verifica
    expected: str        # valor esperado
    origin: str          # de dónde sale el valor esperado
    formula: str = ""    # fórmula de contraste, si aplica


@dataclass
class Interpretation:
    criterion_id: str
    criterion_name: str
    understood_as: str
    steps: list[InterpStep] = field(default_factory=list)
    assertion: Optional[InterpAssertion] = None
    assumptions: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Interpretation":
        steps = [InterpStep(**s) for s in d.get("steps", [])]
        assertion = d.get("assertion")
        return cls(
            criterion_id=d["criterion_id"],
            criterion_name=d.get("criterion_name", ""),
            understood_as=d.get("understood_as", ""),
            steps=steps,
            assertion=InterpAssertion(**assertion) if assertion else None,
            assumptions=d.get("assumptions", []),
            unknowns=d.get("unknowns", []),
            confidence=d.get("confidence", 0.0),
        )

    def one_line(self) -> str:
        return self.understood_as


ACTION_VERBS = {
    "goto": "Abro",
    "fill": "Escribo",
    "select": "Selecciono",
    "click": "Hago click en",
    "submit": "Envío",
    "assert": "Verifico",
}


def render_markdown(interp: Interpretation) -> str:
    """Human-readable block for plan.md / summary.md / HITL prompt."""
    lines = [f"**Cómo lo entendí:** {interp.understood_as}", ""]
    lines.append("**Qué voy a hacer:**")
    for s in interp.steps:
        verb = ACTION_VERBS.get(s.action, s.action)
        detail = f" — {s.detail}" if s.detail else ""
        lines.append(f"   {s.order}. {verb} {s.target}{detail}")
    if interp.assertion:
        a = interp.assertion
        lines.append(f"**Qué voy a verificar:** {a.what} == `{a.expected}`")
        lines.append(f"   origen del valor: {a.origin}")
        if a.formula:
            lines.append(f"   contraste: {a.formula}")
    if interp.assumptions:
        lines.append(f"**Supuestos:** {'; '.join(interp.assumptions)}")
    if interp.unknowns:
        lines.append(f"**No resuelto:** {'; '.join(interp.unknowns)}")
    lines.append(f"**Confianza:** {interp.confidence:.2f}")
    return "\n".join(lines)
