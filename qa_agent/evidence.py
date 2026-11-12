"""Evidence helpers: placeholder images for checks that never opened a screen.

A check that ends BLOCKED without navigating leaves the browser on
about:blank; a raw screenshot there is a useless white image. This module
renders a readable placeholder instead (Pillow; graceful fallback to
"no image" when Pillow is unavailable).
"""
from __future__ import annotations

from pathlib import Path

_PLACEHOLDER_W, _PLACEHOLDER_H = 1280, 720


def is_blank_page(session) -> bool:
    """True when the browser never navigated (about:blank)."""
    try:
        return session.current_url() == "about:blank"
    except Exception:
        return True


def placeholder_png(path: Path, title: str, subtitle: str) -> bool:
    """Draw a readable 'no visual evidence' card. False if Pillow is missing."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False

    img = Image.new("RGB", (_PLACEHOLDER_W, _PLACEHOLDER_H), "#f5f7fb")
    d = ImageDraw.Draw(img)
    d.rectangle([48, 48, _PLACEHOLDER_W - 48, _PLACEHOLDER_H - 48],
                outline="#1a3a6b", width=4)
    d.text((96, 140), "SIN EVIDENCIA VISUAL", fill="#1a3a6b")
    d.text((96, 210), "El check se detuvo antes de abrir una pantalla.",
           fill="#444444")
    d.text((96, 300), title, fill="#222222")
    d.text((96, 360), subtitle, fill="#666666")
    d.text((96, 620), "Laboratorio QA - generado automaticamente", fill="#999999")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return True
