"""Voz do Jarvis: Piper (offline, pt-BR)."""
from __future__ import annotations

import re

import numpy as np

from . import config

_EMOJI = re.compile(
    "[" "\U0001f300-\U0001faff" "\U0001f000-\U0001f2ff" "\u2600-\u27bf" "\ufe0f" "]+"
)
_URL = re.compile(r"https?://\S+")
_MARKUP = re.compile(r"[*_`#>|]+")
_MULTI = re.compile(r"\s+")

_REPLACEMENTS = (
    (r"\bsr\.?\b", "senhor"),
    (r"\bsra\.?\b", "senhora"),
    (r"\bvc\b", "você"),
    (r"\bqdo\b", "quando"),
    (r"\bqtos?\b", "quantos"),
    (r"\bex\.?\b", "por exemplo"),
    (r"\betc\.?\b", "etcétera"),
)


def clean_for_speech(text: str) -> str:
    """Deixa o texto falável: sem markdown, emojis, URLs ou abreviações."""
    text = _URL.sub("", text)
    text = _EMOJI.sub("", text)
    text = _MARKUP.sub("", text)
    for pattern, repl in _REPLACEMENTS:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    text = text.replace("—", ", ").replace("–", ", ")
    return _MULTI.sub(" ", text).strip()


def split_sentences(text: str, max_len: int = 180) -> list[str]:
    """Divide em frases para sintetizar e falar sem esperar o texto inteiro."""
    parts = re.split(r"(?<=[.!?…:;])\s+", text.strip())
    out: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        while len(part) > max_len:
            cut = part.rfind(" ", 0, max_len)
            cut = cut if cut > 40 else max_len
            out.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            out.append(part)
    return out or ([text] if text else [])


class PiperTTS:
    def __init__(self, model_path=config.PIPER_VOICE):
        self.model_path = str(model_path)
        self._voice = None
        self.sr = 22050

    def load(self) -> None:
        if self._voice is None:
            from piper import PiperVoice

            self._voice = PiperVoice.load(self.model_path)
            self.sr = self._voice.config.sample_rate

    def synth(self, text: str) -> np.ndarray:
        text = clean_for_speech(text)
        if not text:
            return np.zeros(0, dtype=np.float32)
        self.load()
        pcm = b"".join(chunk.audio_int16_bytes for chunk in self._voice.synthesize(text))
        return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
