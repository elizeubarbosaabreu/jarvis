"""Aplicativo de terminal do Jarvis: rosto ASCII + conversa por voz."""
from __future__ import annotations

import argparse
import fcntl
import os
import re
import sys
import threading
import time
from pathlib import Path

from . import config
from .audio import Mic, load_wav, play, record_utterance
from .brain import Brain
from .face import FaceState, Screen
from .skills import Skills
from .stt import WhisperSTT
from .tts import PiperTTS, split_sentences
from .util import normalize

GREETING = "Sistemas online. Em que posso ajudar, senhor?"


def render_loop(screen: Screen, state: FaceState, fps: float = 20.0) -> None:
    interval = 1.0 / fps
    while state.live:
        try:
            screen.draw()
        except Exception:
            pass
        time.sleep(interval)


class JarvisApp:
    def __init__(self, greet: bool = True, quiet: bool = False, demo_wav: str | None = None):
        self.state = FaceState()
        self.demo_audio = load_wav(demo_wav) if demo_wav else None
        self.demo_only = demo_wav is not None
        self.stt = WhisperSTT()
        self.tts = PiperTTS()
        self.brain = Brain()
        self.skills = Skills()
        self.mic: Mic | None = None
        self.greet = greet
        self.quiet = quiet
        self.last_said = ""

    # -- fala -------------------------------------------------------------
    def _speak_sentence(self, sentence: str) -> None:
        sentence = sentence.strip()
        if not sentence or self.quiet:
            return
        audio = self.tts.synth(sentence)
        if audio.size:
            play(audio, self.tts.sr, on_level=lambda v: setattr(self.state, "level", v))

    def say_stream(self, chunks) -> None:
        """Fala enquanto o texto chega, frase por frase."""
        state = self.state
        state.set(mode="speaking", said="", level=0.0)
        buffer = ""
        for chunk in chunks:
            buffer += chunk
            state.said = buffer.strip()
            while True:
                match = re.search(r"(?<=[.!?…])\s+", buffer)
                if not match:
                    break
                sentence, buffer = buffer[: match.end()], buffer[match.end():]
                self._speak_sentence(sentence)
        if buffer.strip():
            self._speak_sentence(buffer)
        state.set(level=0.0)

    def say(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.last_said = text
        self.state.set(mode="speaking", said=text, level=0.0)
        if self.quiet:
            time.sleep(min(2.0, 0.02 * len(text)))
            self.state.set(level=0.0)
            return
        for sentence in split_sentences(text):
            audio = self.tts.synth(sentence)
            if audio.size == 0:
                continue
            play(audio, self.tts.sr, on_level=lambda v: setattr(self.state, "level", v))
        self.state.set(level=0.0)

    # -- ciclo ------------------------------------------------------------
    def run(self) -> int:
        state = self.state
        lock_fd = os.open(config.LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("O Jarvis já está aberto em outro terminal.", file=sys.stderr)
            return 1
        with Screen(state) as screen:
            renderer = threading.Thread(
                target=render_loop, args=(screen, state), daemon=True
            )
            renderer.start()

            state.set(mode="boot", note="inicializando núcleos")
            time.sleep(0.4)
            self.tts.load()
            state.set(note="carregando reconhecimento de fala")
            loader = threading.Thread(target=self.stt.load, daemon=True)
            loader.start()
            loader.join(timeout=25)

            state.set(mode="idle", note="")
            if self.greet and not self.quiet:
                self.say(GREETING)

            if self.demo_only:
                state.set(mode="idle", note="modo de teste (wav)")
                return self.loop()

            try:
                self.mic = Mic().open()
            except Exception as exc:
                state.set(mode="error", note=f"microfone indisponível: {exc}")
                time.sleep(4)
                return 2

            try:
                return self.loop()
            finally:
                self.mic.close()

    def loop(self) -> int:
        state = self.state
        idle_since = time.time()

        while True:
            state.set(mode="listening", heard="", said="", level=0.0, look=(0, 0))
            if self.demo_audio is not None:
                audio, self.demo_audio = self.demo_audio, None
                state.set(mode="thinking")
            else:
                self.mic.flush()
                audio = record_utterance(self.mic, state)

            if audio is None:
                if config.IDLE_TIMEOUT_S and time.time() - idle_since > config.IDLE_TIMEOUT_S:
                    self.say("Entrando em repouso, senhor. Chame quando precisar.")
                    return 0
                state.set(mode="idle")
                continue

            idle_since = time.time()
            state.set(mode="thinking", level=0.0, heard="")
            text = self.stt.transcribe(audio)
            text = (text or "").strip()

            if not text:
                state.set(mode="idle", note="Não entendi. Pode repetir, senhor?")
                time.sleep(1.0)
                continue

            state.set(heard=text)

            norm = normalize(text)
            if any(word in norm for word in config.EXIT_WORDS) and len(norm) < 40:
                self.say("Até logo, senhor.")
                return 0

            handled = self.skills.handle(text)
            if handled:
                self.say(handled)
                continue

            if norm in ("repita", "repete", "pode repetir") and self.last_said:
                self.say(self.last_said)
                continue

            self.say_stream(self.brain.ask_stream(text))
            self.last_said = self.brain.last_reply
            if self.demo_only:
                time.sleep(1.0)
                return 0


def selftest() -> int:
    """Testa STT -> cérebro -> voz sem depender do microfone."""
    from .tts import PiperTTS

    tts = PiperTTS()
    tts.load()
    print("1) sintetizando pergunta...")
    audio = tts.synth("Olá Jarvis, que horas são agora?")
    print(f"   {audio.size / tts.sr:.2f}s de áudio")

    print("2) transcrevendo...")
    stt = WhisperSTT()
    t0 = time.time()
    text = stt.transcribe(audio)
    print(f"   {time.time() - t0:.2f}s -> {text!r}")

    print("3) consultando o cérebro...")
    brain = Brain()
    t0 = time.time()
    reply = brain.ask(text or "Olá Jarvis, tudo bem?")
    print(f"   {time.time() - t0:.2f}s [{brain.last_source}] -> {reply!r}")

    print("4) sintetizando resposta...")
    out = tts.synth(reply)
    print(f"   {out.size / tts.sr:.2f}s")

    print("5) tocando...")
    play(out, tts.sr)
    print("ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jarvis por voz")
    parser.add_argument("--no-greet", action="store_true", help="não cumprimentar ao abrir")
    parser.add_argument("--quiet", action="store_true", help="sem áudio (só tela)")
    parser.add_argument("--selftest", action="store_true", help="teste do pipeline")
    parser.add_argument("--demo-wav", help="usa um WAV como se fosse a fala (teste)")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    app = JarvisApp(greet=not args.no_greet, quiet=args.quiet, demo_wav=args.demo_wav)
    try:
        return app.run()
    except KeyboardInterrupt:
        return 0
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h")
        sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
