"""Rosto ASCII animado do Jarvis."""
from __future__ import annotations

import math
import random
import re
import shutil
import sys
import textwrap
import time

HEAD_INNER_W = 52
HEAD_INNER_H = 11
HEAD_W = HEAD_INNER_W + 2
EYE_W = 11
EYE_GAP = 15

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

PALETTE = {
    "border": (0, 122, 145),
    "dim": (62, 84, 96),
    "muted": (118, 148, 162),
    "eye": (150, 246, 255),
    "pupil": (255, 255, 255),
    "accent": (0, 224, 255),
    "mouth": (0, 196, 220),
    "text": (198, 214, 222),
    "warn": (255, 190, 90),
    "ok": (120, 255, 190),
    "bad": (255, 120, 120),
}

MODE_STYLE = {
    "boot": ("INICIANDO", "warn"),
    "idle": ("EM ESPERA", "muted"),
    "listening": ("OUVINDO", "ok"),
    "thinking": ("PROCESSANDO", "warn"),
    "speaking": ("FALANDO", "accent"),
    "sleeping": ("REPOUSO", "dim"),
    "error": ("FALHA", "bad"),
}

MODE_HINT = {
    "boot": "carregando núcleos",
    "idle": "fale para continuar",
    "listening": "fale agora — pausa encerra o comando",
    "thinking": "consultando o núcleo de linguagem",
    "speaking": "fale depois que eu terminar",
    "sleeping": "em repouso — Ctrl+C encerra",
    "error": "verifique microfone e conexão",
}


def fg(text: str, key: str) -> str:
    r, g, b = PALETTE[key]
    return f"\x1b[38;2;{r};{g};{b}m{text}\x1b[0m"


def plain_len(text: str) -> int:
    return len(ANSI_RE.sub("", text))


class FaceState:
    """Estado compartilhado entre a lógica e o desenho."""

    def __init__(self) -> None:
        self.mode = "boot"
        self.level = 0.0
        self.heard = ""
        self.said = ""
        self.note = ""
        self.look: tuple[int, int] | None = None
        self.live = True

    def set(self, **kw) -> None:
        for k, v in kw.items():
            setattr(self, k, v)


def _eye(openness: str, dx: int, dy: int) -> list[tuple[str, str]]:
    w = EYE_W
    top = "╭" + "─" * (w - 2) + "╮"
    bot = "╰" + "─" * (w - 2) + "╯"
    blank = "│" + " " * (w - 2) + "│"

    if openness == "blink":
        return [("▁" * w, "dim")]

    def pupil_row(offset: int) -> tuple[str, str]:
        inner = [" "] * (w - 2)
        pos = max(1, min(w - 3, 4 + offset))
        inner[pos] = "◉"
        return ("│" + "".join(inner) + "│", "eye")

    if openness == "half":
        return [(top, "border"), pupil_row(dx), (bot, "border")]

    rows: list[tuple[str, str]] = [(top, "border")]
    for i in range(3):
        if i == 1 + dy:
            rows.append(pupil_row(dx))
        else:
            rows.append((blank, "border"))
    rows.append((bot, "border"))
    return rows


def _pad_eye(rows: list[tuple[str, str]], height: int = 5) -> list[tuple[str, str]]:
    pad = height - len(rows)
    if pad <= 0:
        return rows[:height]
    top = pad // 2
    blank = (" " * EYE_W, "dim")
    return [blank] * top + rows + [blank] * (pad - top)


def _mouth(amp: float, mode: str) -> list[tuple[str, str]]:
    if mode == "speaking":
        if amp < 0.12:
            w, h = 8, 1
        elif amp < 0.4:
            w, h = 12, 1
        elif amp < 0.7:
            w, h = 16, 2
        else:
            w, h = 20, 3
        if h == 1:
            return [("▐" + "█" * (w - 2) + "▌", "mouth")]
        if h == 2:
            return [("▄" * (w - 2), "mouth"), ("█" * (w - 2), "mouth")]
        return [
            ("▄" * (w - 6), "mouth"),
            ("█" * (w - 2), "mouth"),
            ("▀" * (w - 6), "mouth"),
        ]
    if mode == "thinking":
        return [("▁" * 6, "warn")]
    if mode == "listening":
        return [("▁" * 8, "ok")]
    return [("▁" * 10, "dim")]


class Face:
    def __init__(self, state: FaceState):
        self.state = state
        self.t0 = time.time()
        self._next_blink = time.time() + random.uniform(2.0, 4.5)
        self._blink_until = 0.0
        self._bars = [0.0] * 48
        self._spin = 0

    # -- peças ------------------------------------------------------------
    def _status_badge(self, mode: str) -> str:
        label, key = MODE_STYLE.get(mode, MODE_STYLE["idle"])
        spinner = "◜◝◞◟"[self._spin % 4] if mode == "thinking" else "●"
        return f"{spinner} {label}"

    def _head(self, mode: str, amp: float, openness: str, dx: int, dy: int) -> list[str]:
        inner: list[list[tuple[str, str]]] = []

        def blank(n: int = 1):
            for _ in range(n):
                inner.append([(" " * HEAD_INNER_W, "dim")])

        blank(1)

        eyes = _pad_eye(_eye(openness, dx, dy))
        left, right = eyes, eyes
        total = EYE_W * 2 + EYE_GAP
        margin = (HEAD_INNER_W - total) // 2
        for i in range(5):
            seg = [(" " * margin, "dim"), left[i], (" " * EYE_GAP, "dim"), right[i]]
            inner.append(seg)

        blank(1)

        mouth = _mouth(amp, mode)
        for row in mouth:
            m = (HEAD_INNER_W - len(row[0])) // 2
            inner.append([(" " * m, "dim"), row])

        while len(inner) < HEAD_INNER_H:
            blank()

        lines: list[str] = ["╭" + "─" * HEAD_INNER_W + "╮"]
        for seg in inner[:HEAD_INNER_H]:
            body = "".join(fg(text, key) for text, key in seg)
            pad = HEAD_INNER_W - sum(len(t) for t, _ in seg)
            lines.append(fg("│", "border") + body + " " * pad + fg("│", "border"))
        lines.append("╰" + "─" * HEAD_INNER_W + "╯")
        return [fg(line, "border") if "\x1b" not in line else line for line in lines]

    def _bars_row(self, width: int) -> str:
        glyphs = " ▁▂▃▄▅▆▇█"
        self._bars = self._bars[1:] + [self.state.level]
        n = 40
        values = self._bars[-n:]
        half = n // 2
        ordered = list(reversed(values[:half])) + values[half:]
        base = 0.14 + 0.07 * math.sin(time.time() * 1.3)
        text = "".join(glyphs[min(8, int(max(v, base) * 8.99))] for v in ordered)
        left = max(0, (width - n) // 2)
        return " " * left + fg(text, "accent")

    def _panel(self, width: int, mode: str) -> list[str]:
        state = self.state
        out: list[str] = []
        inner_w = max(20, width - 16)

        if state.heard:
            lines = textwrap.wrap(state.heard, inner_w)[:2] or [""]
            out.append(fg("  você    ", "dim") + fg("▸ ", "ok") + fg(lines[0], "text"))
            for extra in lines[1:]:
                out.append(" " * 12 + fg(extra, "text"))

        if state.said:
            lines = textwrap.wrap(state.said, inner_w)[:3] or [""]
            out.append(fg("  jarvis  ", "dim") + fg("▸ ", "accent") + fg(lines[0], "text"))
            for extra in lines[1:]:
                out.append(" " * 12 + fg(extra, "text"))
        elif state.note:
            out.append(fg("  jarvis  ", "dim") + fg("▸ ", "accent") + fg(state.note, "text"))

        return out

    # -- quadro -----------------------------------------------------------
    def render(self, width: int | None = None, height: int | None = None) -> str:
        state = self.state
        now = time.time()
        term = shutil.get_terminal_size((88, 26))
        width = max(64, min(width or term.columns, 110))
        height = height or term.lines

        if now > self._next_blink:
            self._blink_until = now + 0.12
            self._next_blink = now + random.uniform(2.6, 6.4)
        self._spin += 1

        mode = state.mode
        amp = max(0.0, min(1.0, state.level))

        # olhar
        if state.look is not None:
            dx, dy = state.look
        elif mode in ("thinking",):
            dx, dy = -2, -1
        elif mode in ("listening", "speaking"):
            dx, dy = 0, 0
        else:
            dx = int(round(2 * math.sin(now / 3.7)))
            dy = int(round(math.sin(now / 5.3)))

        if now < self._blink_until:
            openness = "blink"
        elif mode in ("thinking", "listening"):
            openness = "half" if mode == "thinking" else "open"
        else:
            openness = "open"

        head = self._head(mode, amp, openness, dx, dy)
        head_pad = max(0, (width - HEAD_W) // 2)
        head = [" " * head_pad + line for line in head]

        clock = time.strftime("%H:%M:%S")
        left = fg("◢ JARVIS", "accent") + fg("  v1.0", "dim")
        badge = fg(self._status_badge(mode), MODE_STYLE.get(mode, MODE_STYLE["idle"])[1])
        right = fg(clock, "dim")
        gap1 = max(1, width - plain_len(left) - plain_len(badge) - plain_len(right) - 2)
        header = left + " " * gap1 + badge + " " * 2 + right

        rule = fg("  " + "─" * (width - 4), "dim")

        lines: list[str] = [header, rule, ""]
        lines += head
        lines += ["", self._bars_row(width), ""]
        lines += self._panel(width, mode)
        lines += ["", fg("  " + MODE_HINT.get(mode, ""), "dim")]

        # cabe na altura do terminal: remove linhas vazias sobrando
        if height and len(lines) > height:
            while len(lines) > height and "" in lines:
                lines.remove("")
            lines = lines[:height]

        return "\n".join(lines)


class Screen:
    """Tela alternativa: desenha quadros sem sujar o terminal."""

    def __init__(self, state: FaceState):
        self.state = state
        self.face = Face(state)
        self._active = False

    def __enter__(self) -> "Screen":
        sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
        sys.stdout.flush()
        self._active = True
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._active:
            sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
            self._active = False

    def draw(self) -> None:
        if not self._active:
            return
        frame = self.face.render()
        sys.stdout.write("\x1b[H" + frame + "\x1b[J")
        sys.stdout.flush()
