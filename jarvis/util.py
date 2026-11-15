"""Utilidades de texto compartilhadas."""
from __future__ import annotations

import re
import unicodedata


def strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )


def normalize(text: str) -> str:
    """minúsculas, sem acentos, sem pontuação, espaços simples."""
    text = strip_accents(text.lower())
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def has_any(text: str, words) -> bool:
    norm = normalize(text)
    return any(w in norm for w in words)
