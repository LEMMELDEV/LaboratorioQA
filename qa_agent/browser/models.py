"""Pydantic models for page observations and the discovered site map."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class FormField(BaseModel):
    ref: str
    tag: str
    type: str = ""
    name: str = ""          # form field name attribute
    role: str = ""
    label: str = ""         # human-readable label
    required: bool = False
    checked: Optional[bool] = None
    min: Optional[str] = None
    max: Optional[str] = None
    options: list[str] = Field(default_factory=list)


class FormInfo(BaseModel):
    form_id: str = ""
    action: str = ""
    method: str = "get"
    fields: list[FormField] = Field(default_factory=list)


class Element(BaseModel):
    ref: str
    tag: str
    role: str
    name: str = ""          # accessible name
    text: str = ""          # visible text (truncated)
    href: Optional[str] = None
    form_id: Optional[str] = None
    form_action: Optional[str] = None
    form_method: Optional[str] = None
    field_name: Optional[str] = None
    value: Optional[str] = None
    checked: Optional[bool] = None
    disabled: bool = False
    required: bool = False
    min: Optional[str] = None
    max: Optional[str] = None
    options: list[str] = Field(default_factory=list)


class PageObservation(BaseModel):
    """What the agent is allowed to 'see' on the current page."""
    url: str
    title: str
    headings: list[str] = Field(default_factory=list)
    elements: list[Element] = Field(default_factory=list)
    forms: list[FormInfo] = Field(default_factory=list)

    def summary(self) -> str:
        """Compact text rendering (used later as agent context)."""
        lines = [f"URL: {self.url}", f"TITLE: {self.title}"]
        if self.headings:
            lines.append("HEADINGS: " + " | ".join(self.headings[:8]))
        lines.append("ELEMENTS:")
        for e in self.elements:
            bits = [f"[{e.ref}]", e.role, f'"{e.name}"']
            if e.tag not in (e.role,):
                bits.append(f"tag={e.tag}")
            if e.href:
                bits.append(f"href={e.href}")
            if e.value not in (None, ""):
                bits.append(f"value={e.value!r}")
            if e.required:
                bits.append("required")
            if e.disabled:
                bits.append("disabled")
            if e.options:
                bits.append("options=" + "|".join(e.options[:6]))
            lines.append("  " + " ".join(bits))
        for f in self.forms:
            fields = ", ".join(f"{fd.name or fd.ref}({fd.type or fd.tag})" for fd in f.fields)
            lines.append(f"FORM id={f.form_id or '-'} action={f.action or '-'} method={f.method} fields: {fields}")
        return "\n".join(lines)


class Link(BaseModel):
    href: str
    text: str = ""
    status: Optional[int] = None          # filled after navigation attempt
    final_url: Optional[str] = None
    found_on: list[str] = Field(default_factory=list)  # pages where the link appears


class PageRecord(BaseModel):
    url: str
    final_url: str
    status: int
    depth: int
    title: str = ""
    h1: str = ""
    links: list[Link] = Field(default_factory=list)
    forms: list[FormInfo] = Field(default_factory=list)
    elements: list[Element] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class SiteMap(BaseModel):
    base_url: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    bug_profile: str = "none"
    pages: list[PageRecord] = Field(default_factory=list)
    graph: dict[str, list[str]] = Field(default_factory=dict)
    broken_links: list[Link] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)

    def paths(self) -> list[str]:
        seen: set[str] = set()
        for p in self.pages:
            seen.add(_path_of(p.url))
        return sorted(seen)

    def find_page(self, path: str) -> Optional[PageRecord]:
        for p in self.pages:
            if _path_of(p.url) == path:
                return p
        return None


def _path_of(url: str) -> str:
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    q = f"?{parts.query}" if parts.query else ""
    return f"{parts.path}{q}"
