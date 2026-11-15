"""Cérebro do Jarvis: NVIDIA NIM (nuvem) com reserva local no Ollama."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

import requests

from . import config
from .util import normalize

WEEKDAYS = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)

_OPENCODE_AUTH = Path.home() / ".local" / "share" / "opencode" / "auth.json"

OFFLINE_LINE = "Meus circuitos de linguagem não responderam, senhor. Tente novamente."


def _api_key() -> str | None:
    key = os.getenv("JARVIS_NVIDIA_KEY") or os.getenv("NVIDIA_API_KEY")
    if key:
        return key.strip()
    try:
        data = json.loads(_OPENCODE_AUTH.read_text())
        return data.get("nvidia", {}).get("key")
    except Exception:
        return None


_MOJIBAKE = re.compile(r"[ÃÂ][\u0080-\u00bf]")


def _fix_mojibake(text: str) -> str:
    """Conserta texto UTF-8 que foi lido como latin-1 (ex.: "NÃ£o" -> "Não")."""
    if not text or not _MOJIBAKE.search(text):
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _tidy(reply: str) -> str:
    reply = _fix_mojibake((reply or "").strip())
    reply = re.sub(r"^(jarvis|assistente)\s*[:\-]\s*", "", reply, flags=re.IGNORECASE)
    reply = reply.replace("**", "").replace("*", "")
    reply = re.sub(r"[`>#]+", "", reply)
    reply = re.sub(r"\n{2,}", "\n", reply)
    return reply.strip()


class Brain:
    """Conversa com memória curta, streaming e alguns reflexos locais."""

    def __init__(self, timeout: float = config.LLM_TIMEOUT_S):
        self.timeout = timeout
        self.history: list[dict] = []
        self.key = _api_key()
        self.last_source = "?"
        self.last_reply = ""

    # -- reflexos locais (instantâneos, sem rede) -------------------------
    def _reflex(self, text: str) -> str | None:
        n = normalize(text)
        now = datetime.now()
        if any(w in n for w in ("que horas", "hora agora", "horas agora", "que hora")):
            return f"São {now.strftime('%H:%M')}, senhor."
        if any(w in n for w in ("que dia", "data de hoje", "data hoje", "dia de hoje")):
            return (
                f"Hoje é {WEEKDAYS[now.weekday()]}, {now.day} de "
                f"{self._month(now.month)} de {now.year}."
            )
        if n in ("obrigado", "obrigada", "valeu", "muito obrigado"):
            return "Sempre às ordens, senhor."
        return None

    @staticmethod
    def _month(m: int) -> str:
        return (
            "janeiro fevereiro março abril maio junho julho agosto "
            "setembro outubro novembro dezembro"
        ).split()[m - 1]

    def _remember(self, user: str, assistant: str) -> None:
        self.history.append({"role": "user", "content": user})
        self.history.append({"role": "assistant", "content": assistant})
        self.history = self.history[-16:]
        self.last_reply = assistant

    # -- conversa ---------------------------------------------------------
    def ask_stream(self, text: str):
        """Gera a resposta em pedaços, para falar antes de terminar."""
        text = text.strip()
        if not text:
            yield "Não entendi, senhor."
            return

        reflex = self._reflex(text)
        if reflex:
            self.last_source = "local"
            self._remember(text, reflex)
            yield reflex
            return

        self.history.append({"role": "user", "content": text})
        self.history = self.history[-16:]

        parts: list[str] = []
        try:
            try:
                for chunk in self._cloud_stream():
                    parts.append(chunk)
                    yield chunk
                self.last_source = "nvidia"
            except Exception:
                for chunk in self._local_stream():
                    parts.append(chunk)
                    yield chunk
                self.last_source = "ollama"
        except Exception:
            parts.append(OFFLINE_LINE)
            self.last_source = "offline"
            yield OFFLINE_LINE

        reply = _tidy("".join(parts))
        if reply:
            self._remember(text, reply)

    def ask(self, text: str) -> str:
        reply = "".join(self.ask_stream(text))
        return _tidy(reply)

    def _messages(self) -> list[dict]:
        return [{"role": "system", "content": config.SYSTEM_PROMPT}, *self.history]

    def _cloud_stream(self):
        if not self.key:
            raise RuntimeError("sem chave da NVIDIA")
        with requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json={
                "model": config.NVIDIA_MODEL,
                "messages": self._messages(),
                "max_tokens": 320,
                "temperature": 0.65,
                "top_p": 0.9,
                "stream": True,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=self.timeout,
            stream=True,
        ) as resp:
            resp.raise_for_status()
            for raw in resp.iter_lines(decode_unicode=False):
                if not raw:
                    continue
                line = raw.decode("utf-8", "replace")
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    delta = obj["choices"][0].get("delta", {}).get("content")
                except Exception:
                    continue
                if delta:
                    yield _fix_mojibake(delta)

    def _local_stream(self):
        with requests.post(
            f"{config.OLLAMA_URL}/api/chat",
            json={
                "model": config.OLLAMA_MODEL,
                "messages": self._messages(),
                "stream": True,
                "options": {"temperature": 0.65, "num_predict": 220},
            },
            timeout=self.timeout,
            stream=True,
        ) as resp:
            resp.raise_for_status()
            for raw in resp.iter_lines(decode_unicode=False):
                if not raw:
                    continue
                try:
                    obj = json.loads(raw.decode("utf-8", "replace"))
                except Exception:
                    continue
                content = obj.get("message", {}).get("content")
                if content:
                    yield _fix_mojibake(content)
                if obj.get("done"):
                    break
