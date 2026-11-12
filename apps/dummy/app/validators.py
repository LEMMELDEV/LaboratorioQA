"""Input validators. BUG branches controlled via defects.is_active()."""
from __future__ import annotations

import re
from typing import Set

# Correct RFC-ish pattern: accepts '+', dots, etc.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
# BUG-04 pattern: '+' is NOT allowed.
_EMAIL_RE_BUG = re.compile(r"^[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def email_error(email: str, *, bugs: Set[str] = frozenset()) -> str:
    """Return an error message for an invalid email, or '' when valid."""
    email = email.strip()
    if not email:
        return "Este campo es obligatorio."
    pattern = _EMAIL_RE_BUG if "BUG-04" in bugs else _EMAIL_RE
    if not pattern.match(email):
        return "Email invalido."
    return ""
