"""Comandos de desktop: abrir, fechar, minimizar, maximizar, volume."""
from __future__ import annotations

import re
import urllib.parse

from . import youtube
from .desktop import Desktop
from .util import normalize

OPEN = r"(?:abrir|abre|abra|iniciar|inicia|inicia|executar|executa|lancar|lanca|roda|rodar)"
CLOSE = r"(?:fechar|fecha|encerrar|encerra|matar|mata|finalizar|finaliza|sair do|sai do)"
MIN = r"(?:minimizar|minimiza|minimize|esconder|esconde|recolher|recolhe)"
MAX = r"(?:maximizar|maximiza|maximize|expandir|expande)"
SHOW = r"(?:mostrar|mostra|abrir|abre|trazer|traz|focar|foca|ativar|ativa|ir para|vai para)"
ALL = r"(?:tudo|todos|todas|todas as janelas|as janelas|as janelas|os programas)"

OPEN_RE = re.compile(rf"^{OPEN}\s+(.+)$")
CLOSE_RE = re.compile(rf"^{CLOSE}\s+(.+)$")
MIN_ALL_RE = re.compile(rf"^{MIN}\s+{ALL}$")
MIN_RE = re.compile(rf"^{MIN}\s+(.+)$")
MAX_RE = re.compile(rf"^{MAX}\s+(.+)$")
SHOW_DESKTOP_RE = re.compile(
    r"^(?:mostrar|mostra|abrir|abre|ir para|vai para)\s+(?:a\s+|o\s+)?"
    r"(?:area de trabalho|desktop|mesa)$"
)
RESTORE_RE = re.compile(
    rf"^(?:restaurar|restaura|mostrar|mostra|trazer|traz|voltar|volta)\s+{ALL}$"
)
LIST_RE = re.compile(
    r"^(?:o que|quais|que)\b.*(?:aberto|abertos|janelas|programas)|"
    r"^(?:listar|lista)\s+(?:as\s+)?(?:janelas|programas)$|"
    r"^(?:janelas|programas)\s+abertos?$"
)
FOCUS_RE = re.compile(rf"^{SHOW}\s+(?!a area)(?!o desktop)(.+)$")

VOL_UP_RE = re.compile(
    r"^(?:aumentar|aumenta|subir|sobe|aumente)\s+(?:o\s+)?volume(?:\s+(?:em\s+|para\s+|a\s+)?(\d+))?$"
)
VOL_DOWN_RE = re.compile(
    r"^(?:diminuir|diminui|baixar|baixa|abaixe|reduzir|reduz)\s+(?:o\s+)?volume"
    r"(?:\s+(?:em\s+|para\s+|a\s+)?(\d+))?$"
)
VOL_SET_RE = re.compile(r"^(?:volume|som)\s+(?:em|para|a)\s+(\d+)(?:\s*por\s*cento)?$")
YT = r"(?:you\s*tube|yutube|yt)"
YT_HOME_RE = re.compile(
    rf"^(?:abrir|abre|abra|ir para|vai para|entrar no|entra no)\s+(?:o\s+)?(?:site\s+do\s+)?{YT}$",
    re.IGNORECASE,
)
YT_MUSIC_RE = re.compile(
    rf"^(?:abrir|abre|abra|ir para|vai para)\s+(?:o\s+)?{YT}\s+music$|"
    r"^(?:tocar|toca|colocar|coloca|passar|passa)\s+(?:uma\s+)?m[uú]sica$",
    re.IGNORECASE,
)
YT_SEARCH_RE = re.compile(
    rf"^(?:pesquisar|pesquisa|buscar|busca|procurar|procura|procurar por)\s+(.+?)\s+"
    rf"(?:no|na|em)\s+{YT}$",
    re.IGNORECASE,
)
YT_PLAY_RE = re.compile(
    rf"^(?:tocar|toca|colocar|coloca|passar|passa|abrir|abre|abra|assistir|assiste|"
    rf"ver|mostrar|mostra)\s+(?:o\s+|a\s+)?(?:v[ií]deo|clipe|m[uú]sica|som)?\s*"
    rf"(?:do\s+|da\s+|de\s+)?(.+?)\s+(?:no|na|em)\s+{YT}$",
    re.IGNORECASE,
)
YT_IMPLICIT_RE = re.compile(
    r"^(?:tocar|toca|colocar|coloca|passar|passa|assistir|assiste|ver|mostrar|mostra|"
    r"abrir|abre|abra)\s+(?:o\s+|a\s+)?(?:v[ií]deo|clipe|m[uú]sica)\s+"
    r"(?:do\s+|da\s+|de\s+)?(.+)$",
    re.IGNORECASE,
)
YT_OUVIR_RE = re.compile(
    rf"^(?:ouvir|ouve|ouça|ouça o|ouvir o|ouvir a)\s+(.+?)(?:\s+(?:no|na|em)\s+{YT})?$",
    re.IGNORECASE,
)
YT_ASSISTIR_RE = re.compile(
    rf"^(?:assistir|assiste|assista|assistir o|assistir a)\s+(.+?)(?:\s+(?:no|na|em)\s+{YT})?$",
    re.IGNORECASE,
)
WRITE_RE = re.compile(
    r"^(?:escreva|escreve|escrever|digite|digita|digitar|anote|anota|"
    r"registre|registra|apontar|aponta|escreva isto|escreva isso)$",
    re.IGNORECASE,
)
WRITE_WITH_TEXT_RE = re.compile(
    r"^(?:escreva|escreve|escrever|digite|digita|digitar|anote|anota|"
    r"registre|registra|apontar|aponta)\s+(.+)$",
    re.IGNORECASE,
)
SHUTDOWN_RE = re.compile(
    r"^(?:desligar|desliga|desligue|encerrar|encerra|encerre|pare|pare o|"
    r"pare tudo|finalizar|finalize|mate o|mata o|matar o|maten o|"
    r"desligue o jarvis|encerre o jarvis|pare o jarvis|desligar o jarvis|"
    r"encerrar o jarvis|desligar tudo|encerrar tudo|desligar completamente|"
    r"encerrar completamente)\s*(?:o jarvis|a tudo|tudo|completamente)?$",
    re.IGNORECASE,
)

MUTE_RE = re.compile(r"^(?:silenciar|silencia|mudo|muta|mutar|tirar o som|sem som)$")
UNMUTE_RE = re.compile(
    r"^(?:ativar|ativa|ligar|liga|voltar|volta|tirar)\s+(?:o\s+)?(?:som|mudo|audio|áudio)$|"
    r"^(?:com som|desmutar|desmuta)$"
)


ARTICLES = {
    "Calculadora": "a",
    "Câmera": "a",
    "Loja de Aplicativos": "a",
    "Captura de Tela": "a",
    "Música": "a",
    "Planilha": "a",
    "Configurações": "as",
    "Arquivos": "os",
}


class Skills:
    """Interpreta comandos de desktop antes de chamar o modelo de linguagem."""

    def __init__(self, desktop: Desktop | None = None):
        self.d = desktop or Desktop()

    @staticmethod
    def _with_article(label: str) -> str:
        return f"{ARTICLES.get(label, 'o')} {label}"

    # -- entrada ----------------------------------------------------------
    def handle(self, text: str) -> str | None:
        norm = normalize(text)
        if not norm:
            return None
        raw = text.strip().rstrip(" .!?,;:")

        if match := YT_MUSIC_RE.match(raw):
            return self._youtube_music()
        if match := YT_HOME_RE.match(raw):
            return self._youtube_home()
        if match := YT_SEARCH_RE.match(raw):
            return self._youtube_search(match.group(1))
        if match := YT_PLAY_RE.match(raw):
            return self._youtube_play(match.group(1))
        if match := YT_IMPLICIT_RE.match(raw):
            return self._youtube_play(match.group(1))
        if match := YT_OUVIR_RE.match(raw):
            return self._youtube_ouvir(match.group(1))
        if match := YT_ASSISTIR_RE.match(raw):
            return self._youtube_assistir(match.group(1))
        if match := WRITE_RE.match(raw):
            return self._write_prompt()
        if match := WRITE_WITH_TEXT_RE.match(raw):
            return self._write(match.group(1))
        if SHUTDOWN_RE.match(norm):
            return self._shutdown()

        if SHOW_DESKTOP_RE.match(norm):
            return self._show_desktop()
        if MIN_ALL_RE.match(norm):
            return self._minimize_all()
        if RESTORE_RE.match(norm):
            return self._restore_all()
        if LIST_RE.match(norm):
            return self._list_windows()
        if MUTE_RE.match(norm):
            return self._mute()
        if UNMUTE_RE.match(norm):
            return self._unmute()
        if match := VOL_UP_RE.match(norm):
            return self._volume(+int(match.group(1) or 10))
        if match := VOL_DOWN_RE.match(norm):
            return self._volume(-int(match.group(1) or 10))
        if match := VOL_SET_RE.match(norm):
            return self._volume_set(int(match.group(1)))
        if match := CLOSE_RE.match(norm):
            return self._close(match.group(1))
        if match := MIN_RE.match(norm):
            return self._minimize(match.group(1))
        if match := MAX_RE.match(norm):
            return self._maximize(match.group(1))
        if match := OPEN_RE.match(norm):
            return self._open(match.group(1))
        if match := FOCUS_RE.match(norm):
            return self._focus(match.group(1))
        return None

    # -- YouTube ----------------------------------------------------------
    @staticmethod
    def _clean_term(term: str) -> str:
        term = term.strip(" \t\"'“”")
        for article in ("o ", "a ", "os ", "as ", "um ", "uma "):
            if term.lower().startswith(article):
                term = term[len(article) :].strip()
                break
        return term

    def _youtube_home(self) -> str:
        if youtube.open_url(youtube.HOME):
            return "Abrindo o YouTube, senhor."
        return "Não consegui abrir o navegador, senhor."

    def _youtube_music(self) -> str:
        if youtube.open_url(youtube.MUSIC):
            return "Abrindo o YouTube Music, senhor."
        return "Não consegui abrir o navegador, senhor."

    def _youtube_search(self, term: str) -> str:
        term = self._clean_term(term)
        if not term:
            return self._youtube_home()
        if youtube.open_url(youtube.search_url(term)):
            return f"Procurando {term} no YouTube, senhor."
        return "Não consegui abrir o navegador, senhor."

    def _youtube_play(self, term: str) -> str:
        term = self._clean_term(term)
        if not term:
            return self._youtube_music()

        video = youtube.first_video(term)
        if video and youtube.open_url(video["url"]):
            title = video.get("title") or term
            if len(title) > 70:
                title = title[:67].rstrip() + "..."
            return f"Tocando {title}, senhor."

        if youtube.open_url(youtube.search_url(term)):
            return f"Não achei um vídeo certo, mas abri a busca por {term}, senhor."
        return "Não consegui abrir o navegador, senhor."

    def _youtube_ouvir(self, term: str) -> str:
        """Ouvi no YouTube Music (busca ou reprodução direta)."""
        term = self._clean_term(term)
        if not term:
            return self._youtube_music()

        music_url = (
            "https://music.youtube.com/search?q=" + urllib.parse.quote_plus(term)
        )
        if youtube.open_url(music_url):
            return f"Procurando {term} no YouTube Music, senhor."
        return "Não consegui abrir o navegador, senhor."

    def _youtube_assistir(self, term: str) -> str:
        """Assiste no YouTube (toca o primeiro resultado da busca)."""
        return self._youtube_play(term)

    # -- escrever (digitação) ---------------------------------------------
    def _write_prompt(self) -> str:
        return "O que o senhor quer que eu escreva?"

    def _write(self, term: str) -> str:
        term = term.strip(" \t\"'“”")
        if not term:
            return self._write_prompt()
        if self.d.write(term):
            return (
                f"Escrevi {term[:60]} na área de transferência e abri o editor, "
                f"senhor. Cole com Ctrl+V."
            )
        return "Não consegui escrever, senhor."

    # -- desligamento completo ---------------------------------------------
    def _shutdown(self) -> str:
        """Encerra o assistente e para o daemon da palavra-chave.

        Deixa run/disabled para o autostart não ressuscitar no login.
        O Jarvis só volta a ser chamado pelo menu, pelo botão do painel
        ou pelo terminal (`jarvis`).
        """
        from . import config

        (config.RUN / "disabled").touch()
        self._stop_wake_daemon()
        return "__jarvis_shutdown__"

    @staticmethod
    def _stop_wake_daemon() -> None:
        """Para o wake_daemon pelo PID do lock e por padrão específico."""
        import os
        import signal
        import subprocess

        from . import config

        subprocess.run(
            ["systemctl", "--user", "stop", "jarvis-wake.service"],
            capture_output=True,
        )

        try:
            pid = int((config.RUN / "wake.lock").read_text().strip())
            os.kill(pid, signal.SIGTERM)
        except (OSError, ValueError):
            pass

        # Só o interpretador do venv rodando o daemon (não editores abertos).
        subprocess.run(
            ["pkill", "-f", r"\.venv/bin/python .*wake_daemon\.py"],
            capture_output=True,
        )

    def _open(self, query: str) -> str:
        app = self.d.resolve(query)
        if app is None:
            return f"Não encontrei nenhum programa chamado {query}, senhor."

        if self.d.window_control:
            result = self.d.activate(app)
            if result.get("count"):
                return f"Trouxe {self._with_article(app.label)} para frente, senhor."

        if self.d.launch(app):
            return f"Abrindo {self._with_article(app.label)}, senhor."
        return f"Não consegui abrir {self._with_article(app.label)}, senhor."

    def _close(self, query: str) -> str:
        app = self.d.resolve(query)
        if app is None:
            return f"Não encontrei nenhum programa chamado {query}, senhor."

        result = self.d.close(app)
        if result.get("count"):
            if result.get("fallback"):
                return f"Encerrei {self._with_article(app.label)}, senhor."
            return f"Fechando {self._with_article(app.label)}, senhor."
        return f"{app.label} não está em execução, senhor."

    def _minimize(self, query: str) -> str:
        app = self.d.resolve(query)
        if app is None:
            return f"Não encontrei nenhum programa chamado {query}, senhor."
        if not self.d.window_control:
            return "Ainda não consigo mexer em janelas, senhor."
        result = self.d.minimize(app)
        if result.get("count"):
            return f"Minimizando {self._with_article(app.label)}, senhor."
        return f"{app.label} não está em execução, senhor."

    def _maximize(self, query: str) -> str:
        app = self.d.resolve(query)
        if app is None:
            return f"Não encontrei nenhum programa chamado {query}, senhor."
        if not self.d.window_control:
            return "Ainda não consigo mexer em janelas, senhor."
        result = self.d.maximize(app)
        if result.get("count"):
            return f"Maximizando {self._with_article(app.label)}, senhor."
        return f"{app.label} não está em execução, senhor."

    def _focus(self, query: str) -> str:
        app = self.d.resolve(query)
        if app is None:
            return f"Não encontrei nenhum programa chamado {query}, senhor."
        if not self.d.window_control:
            return "Ainda não consigo mexer em janelas, senhor."
        result = self.d.activate(app)
        if result.get("count"):
            return f"Trazendo {self._with_article(app.label)}, senhor."
        return f"{app.label} não está em execução, senhor."

    def _minimize_all(self) -> str:
        if not self.d.window_control:
            return "Ainda não consigo mexer em janelas, senhor."
        result = self.d.minimize_all()
        count = result.get("count", 0)
        if count:
            return f"Minimizando {count} janelas, senhor."
        return "Não há janelas abertas, senhor."

    def _show_desktop(self) -> str:
        if not self.d.window_control:
            return "Ainda não consigo mexer em janelas, senhor."
        result = self.d.minimize_all()
        if result.get("count"):
            return "Área de trabalho à mostra, senhor."
        return "A área de trabalho já está limpa, senhor."

    def _restore_all(self) -> str:
        if not self.d.window_control:
            return "Ainda não consigo mexer em janelas, senhor."
        result = self.d.restore_all()
        if result.get("count"):
            return "Trazendo as janelas de volta, senhor."
        return "Não há janelas para restaurar, senhor."

    def _list_windows(self) -> str:
        if not self.d.window_control:
            return "Ainda não consigo ver as janelas, senhor."
        windows = self.d.windows()
        if not windows:
            return "Não há janelas abertas, senhor."
        names: list[str] = []
        for win in windows:
            name = (win.get("app") or win.get("title") or "").strip()
            if name and name not in names:
                names.append(name)
        if not names:
            return "Não consegui identificar as janelas, senhor."
        if len(names) == 1:
            return f"Está aberto o {names[0]}, senhor."
        return "Estão abertos: " + ", ".join(names[:-1]) + f" e {names[-1]}, senhor."

    def _volume(self, delta: int) -> str:
        level = self.d.volume(f"{delta:+d}%")
        if level is None:
            return "Não consegui ajustar o volume, senhor."
        if self.d.muted():
            self.d.volume(mute=False)
        return f"Volume em {level} por cento."

    def _volume_set(self, level: int) -> str:
        level = max(0, min(150, level))
        got = self.d.volume(f"{level}%")
        return f"Volume em {got if got is not None else level} por cento."

    def _mute(self) -> str:
        self.d.volume(mute=True)
        return "Som silenciado, senhor."

    def _unmute(self) -> str:
        self.d.volume(mute=False)
        return "Som de volta, senhor."


def main(argv: list[str] | None = None) -> int:
    import sys

    text = " ".join(argv if argv is not None else sys.argv[1:])
    skills = Skills()
    print(f"janelas controláveis: {skills.d.window_control}")
    print(skills.handle(text) or "(não é um comando de desktop)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
