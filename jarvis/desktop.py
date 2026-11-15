"""Controle do desktop: janelas (extensão GNOME), aplicativos e volume."""
from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from .util import normalize

BUS = "br.jarvis.Control"
OBJ = "/br/jarvis/Control"
IFACE = "br.jarvis.Control"

APP_DIRS = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local" / "share" / "applications",
]

# nomes falados -> candidatos (nome ou id do .desktop)
ALIASES = {
    "navegador": ["brave", "firefox", "chromium", "google chrome"],
    "browser": ["brave", "firefox", "chromium"],
    "internet": ["brave", "firefox", "chromium"],
    "calculadora": ["calculadora", "calculator", "gnome-calculator"],
    "arquivos": ["arquivos", "files", "nautilus"],
    "gerenciador de arquivos": ["arquivos", "files", "nautilus"],
    "pastas": ["arquivos", "files", "nautilus"],
    "terminal": ["terminal", "gnome-terminal"],
    "editor de texto": ["text editor", "editor de textos", "gedit", "gnome-text-editor"],
    "bloco de notas": ["text editor", "gedit", "gnome-text-editor"],
    "arquivo de texto": ["text editor", "gnome-text-editor"],
    "arquivo de textos": ["text editor", "gnome-text-editor"],
    "textos": ["text editor", "gnome-text-editor"],
    "configuracoes": ["configurações", "settings", "gnome-control-center"],
    "ajustes": ["configurações", "settings", "gnome-control-center"],
    "loja": ["loja de aplicativos", "software", "gnome-software"],
    "software": ["loja de aplicativos", "software"],
    "musica": ["rhythmbox", "spotify", "música"],
    "video": ["videos", "totem", "celluloid", "vídeos"],
    "camera": ["cheese", "câmera"],
    "monitor": ["monitor do sistema", "system monitor", "gnome-system-monitor"],
    "captura de tela": ["captura de tela", "screenshot", "gnome-screenshot"],
    "codigo": ["code", "vscode", "visual studio code"],
    "planilha": ["libreoffice calc", "planilha"],
    "documento": ["libreoffice writer", "writer"],
    "pdf": ["evince", "visualizador de documentos"],
    "imagem": ["visualizador de imagens", "eog", "imagens"],
}

NAME_PT = {
    "brave-browser": "Brave",
    "firefox": "Firefox",
    "google-chrome": "Google Chrome",
    "chromium-browser": "Chromium",
    "org.gnome.Calculator": "Calculadora",
    "org.gnome.Nautilus": "Arquivos",
    "org.gnome.Terminal": "Terminal",
    "org.gnome.Settings": "Configurações",
    "org.gnome.TextEditor": "Editor de Texto",
    "org.gnome.Software": "Loja de Aplicativos",
    "org.gnome.SystemMonitor": "Monitor do Sistema",
    "org.gnome.Screenshot": "Captura de Tela",
    "org.gnome.Evince": "Visualizador de Documentos",
    "org.gnome.eog": "Visualizador de Imagens",
    "org.gnome.Cheese": "Câmera",
    "org.gnome.Totem": "Vídeos",
    "org.gnome.Rhythmbox3": "Música",
    "libreoffice-calc": "LibreOffice Calc",
    "libreoffice-writer": "LibreOffice Writer",
    "org.gnome.baobab": "Analisador de Disco",
    "gnome-disks": "Discos",
    "code": "Visual Studio Code",
    "spotify": "Spotify",
}

# nomes de processo que não batem com o nome do .desktop
PROCESS_ALIASES = {
    "brave-browser": ["brave"],
    "brave-browser-stable": ["brave"],
    "brave": ["brave"],
    "google-chrome": ["chrome"],
    "google-chrome-stable": ["chrome"],
    "chromium-browser": ["chromium"],
    "microsoft-edge": ["msedge"],
    "org.telegram.desktop": ["telegram-desktop", "telegram"],
    "com.spotify.Client": ["spotify"],
    "code": ["code"],
    "org.gnome.Console": ["kgx"],
    "org.gnome.Terminal": ["gnome-terminal-", "gnome-terminal"],
}

FILLERS = (
    "o ", "a ", "os ", "as ", "um ", "uma ",
    "programa ", "aplicativo ", "app ", "janela ", "do ", "da ",
    "para mim", "pra mim", "por favor", "agora", "rapido", "rápido",
)


def _clean_query(text: str) -> str:
    q = normalize(text)
    q = re.sub(r"\b(para mim|pra mim|por favor|agora|mesmo)\b", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    changed = True
    while changed:
        changed = False
        for filler in FILLERS:
            f = normalize(filler)
            if q.startswith(f + " ") or q == f:
                q = q[len(f) :].strip()
                changed = True
    return q


@dataclass
class App:
    id: str
    name: str
    exec: str = ""
    generic: str = ""
    keywords: str = ""
    terminal: bool = False
    wm_class: str = ""
    path: Path | None = None

    @property
    def label(self) -> str:
        base = self.name.split(" — ")[0].split(" - ")[0].strip()
        return NAME_PT.get(self.id, NAME_PT.get(base, base))


@dataclass
class Desktop:
    """Fachada para janelas e aplicativos. Degrada sem a extensão do Shell."""

    apps: list[App] = field(default_factory=list)
    _available: bool | None = None

    def __post_init__(self) -> None:
        self.apps = self._scan_apps()

    # -- catálogo ---------------------------------------------------------
    def _scan_apps(self) -> list[App]:
        seen: set[str] = set()
        apps: list[App] = []
        for directory in APP_DIRS:
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*.desktop")):
                try:
                    app = self._parse_desktop(path)
                except Exception:
                    continue
                if app is None or app.id in seen:
                    continue
                seen.add(app.id)
                apps.append(app)
        return apps

    @staticmethod
    def _parse_desktop(path: Path) -> App | None:
        data: dict[str, str] = {}
        in_entry = False
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                in_entry = line == "[Desktop Entry]"
                continue
            if not in_entry or "=" not in line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            data.setdefault(key.strip(), value.strip())

        if data.get("Type", "Application") != "Application":
            return None
        if data.get("NoDisplay", "").lower() == "true" or data.get("Hidden", "").lower() == "true":
            return None
        name = data.get("Name[pt_BR]") or data.get("Name") or path.stem
        rel = path
        for directory in APP_DIRS:
            try:
                rel = path.relative_to(directory)
                break
            except ValueError:
                continue
        app_id = str(rel.with_suffix(""))
        return App(
            id=app_id,
            name=name,
            exec=data.get("Exec", ""),
            generic=data.get("GenericName[pt_BR]") or data.get("GenericName", ""),
            keywords=data.get("Keywords[pt_BR]") or data.get("Keywords", ""),
            terminal=data.get("Terminal", "").lower() == "true",
            wm_class=data.get("StartupWMClass", ""),
            path=path,
        )

    def resolve(self, query: str) -> App | None:
        q = _clean_query(query)
        if not q:
            return None

        # apelidos falados
        for key, candidates in ALIASES.items():
            k = normalize(key)
            if q == k or q.startswith(k + " ") or q.endswith(" " + k):
                for candidate in candidates:
                    found = self._exact(candidate)
                    if found:
                        return found

        best: App | None = None
        best_score = 0.0
        for app in self.apps:
            score = self._score(q, app)
            if score > best_score:
                best, best_score = app, score
        if best_score >= 58:
            return best

        # fala ruidosa ("o brave aí", "brave pra mim"): tenta palavra por palavra
        tokens = [t for t in re.split(r"[^a-z0-9]+", q) if len(t) >= 3]
        for token in sorted(tokens, key=len, reverse=True):
            for app in self.apps:
                score = self._score(token, app)
                if score > best_score:
                    best, best_score = app, score
        return best if best_score >= 72 else None

    def _exact(self, candidate: str) -> App | None:
        c = normalize(candidate)
        for app in self.apps:
            names = {
                normalize(app.name),
                normalize(app.label),
                normalize(app.id),
                normalize(app.id.split(".")[-1]),
            }
            if c in names:
                return app
        for app in self.apps:
            if c in normalize(app.name) or c in normalize(app.id):
                return app
        return None

    @staticmethod
    def _score(q: str, app: App) -> float:
        names = [
            normalize(app.name),
            normalize(app.label),
            normalize(app.generic),
            normalize(app.id),
            normalize(app.id.split(".")[-1]),
            normalize(Path(shlex.split(app.exec)[0]).name if app.exec else ""),
        ]
        best = 0.0
        for name in names:
            if not name:
                continue
            if q == name:
                return 100.0
            if name.startswith(q):
                best = max(best, 92.0)
            elif q in name:
                best = max(best, 86.0)
            else:
                ratio = SequenceMatcher(None, q, name).ratio()
                best = max(best, ratio * 70.0)
        for word in re.split(r"[,\s;]+", normalize(app.keywords)):
            if word and (word == q or word.startswith(q)):
                best = max(best, 78.0)
        return best

    # -- janelas (extensão GNOME) ----------------------------------------
    def _call(self, method: str, *args: str) -> dict | None:
        argv = ["busctl", "--user", "--json=short", "call", BUS, OBJ, IFACE, method]
        for arg in args:
            argv += ["s", arg]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        try:
            envelope = json.loads(proc.stdout)
            return json.loads(envelope["data"][0])
        except Exception:
            return None

    @property
    def window_control(self) -> bool:
        if self._available is None:
            self._available = self._call("List") is not None
        return bool(self._available)

    def windows(self) -> list[dict]:
        data = self._call("List")
        return data.get("windows", []) if data else []

    def close(self, app: App) -> dict:
        if self.window_control:
            result = self._call("Close", app.label) or self._call("Close", app.name) or {}
            if result.get("count"):
                return result
        # reserva: encerra os processos do aplicativo
        killed = self._terminate_processes(app)
        return {"ok": killed > 0, "count": killed, "windows": [], "fallback": True}

    def minimize(self, app: App) -> dict:
        return self._call("Minimize", app.label) or {}

    def unminimize(self, app: App) -> dict:
        return self._call("Unminimize", app.label) or {}

    def activate(self, app: App) -> dict:
        return self._call("Activate", app.label) or {}

    def maximize(self, app: App) -> dict:
        return self._call("Maximize", app.label) or {}

    def minimize_all(self) -> dict:
        return self._call("MinimizeAll") or {}

    def restore_all(self) -> dict:
        return self._call("RestoreAll") or {}

    def _process_tokens(self, app: App) -> set[str]:
        """Nomes pelos quais os processos deste aplicativo podem aparecer."""
        names: set[str] = set()
        if app.exec:
            try:
                names.add(Path(shlex.split(app.exec)[0]).name)
            except Exception:
                pass
        names.add(Path(app.id).name)
        if app.wm_class:
            names.add(app.wm_class)
        for extra in PROCESS_ALIASES.get(app.id, []):
            names.add(extra)
        for extra in PROCESS_ALIASES.get(Path(app.id).name, []):
            names.add(extra)

        tokens: set[str] = set()
        for name in names:
            name = name.strip().lower()
            if not name:
                continue
            tokens.add(name)
            for suffix in ("-stable", "-bin", ".bin", "-desktop"):
                if name.endswith(suffix) and len(name) > len(suffix) + 3:
                    tokens.add(name[: -len(suffix)])
        return {t for t in tokens if len(t) >= 4}

    @staticmethod
    def _alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _find_processes(self, tokens: set[str]) -> list[int]:
        if not tokens:
            return []
        mine = {os.getpid(), os.getppid(), os.getpgrp()}
        found: list[int] = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid in mine:
                continue
            try:
                if os.getpgid(pid) in mine:
                    continue
                comm = (entry / "comm").read_text().strip()
                raw = (entry / "cmdline").read_bytes()
                cmdline = raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
                exe = Path(os.readlink(entry / "exe")).name
            except OSError:
                continue
            if "jarvis.app" in cmdline or "wake_daemon" in cmdline:
                continue

            argv0 = Path(cmdline.split(" ", 1)[0]).name if cmdline else ""
            for tok in tokens:
                if (
                    exe == tok
                    or argv0 == tok
                    or comm == tok[:15]
                    or (len(tok) >= 5 and comm.startswith(tok[:15]))
                ):
                    found.append(pid)
                    break
        return found

    def _terminate_processes(self, app: App) -> int:
        tokens = self._process_tokens(app)
        targets = self._find_processes(tokens)
        if not targets:
            return 0

        for pid in targets:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass

        deadline = time.time() + 2.5
        rest = list(targets)
        while rest and time.time() < deadline:
            time.sleep(0.2)
            rest = [pid for pid in rest if self._alive(pid)]
        for pid in rest:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        return len(targets)

    # -- aplicativos ------------------------------------------------------
    def launch(self, app: App) -> bool:
        try:
            subprocess.Popen(
                ["gtk-launch", app.id],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            pass
        if app.path is not None:
            try:
                subprocess.Popen(
                    ["gio", "launch", str(app.path)],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                pass
        if app.exec:
            cmd = re.sub(r"%[fFuUdDnNickvm]", "", app.exec).strip()
            if cmd:
                try:
                    subprocess.Popen(
                        shlex.split(cmd),
                        start_new_session=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return True
                except Exception:
                    return False
        return False

    # -- URLs -------------------------------------------------------------
    @staticmethod
    def open_url(url: str) -> bool:
        """Abre uma URL no navegador padrão do GNOME."""
        for argv in (["gio", "open", url], ["xdg-open", url]):
            try:
                subprocess.Popen(
                    argv,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                continue
        return False

    # -- volume -----------------------------------------------------------
    @staticmethod
    def volume(delta: str | None = None, mute: bool | None = None) -> int | None:
        if mute is not None:
            subprocess.run(
                ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if mute else "0"],
                capture_output=True,
            )
        elif delta:
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", delta],
                capture_output=True,
            )
        try:
            out = subprocess.run(
                ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                capture_output=True,
                text=True,
            ).stdout
            match = re.search(r"(\d+)%", out)
            return int(match.group(1)) if match else None
        except Exception:
            return None

    @staticmethod
    def muted() -> bool:
        out = subprocess.run(
            ["pactl", "get-sink-mute", "@DEFAULT_SINK@"], capture_output=True, text=True
        ).stdout
        return "yes" in out
