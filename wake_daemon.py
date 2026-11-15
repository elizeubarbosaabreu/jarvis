#!/usr/bin/env python3
"""Escuta contínua de "Olá Jarvis" e abre o terminal do assistente.

Roda em segundo plano (autostart). Usa VAD + Whisper pequeno (offline).
Enquanto o aplicativo está aberto, o daemon pausa e libera memória.
"""
from __future__ import annotations

import argparse
import fcntl
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from jarvis import config  # noqa: E402
from jarvis.audio import Mic, record_utterance  # noqa: E402
from jarvis.stt import WhisperSTT  # noqa: E402
from jarvis.util import normalize  # noqa: E402

WAKE_VARIANTS = ("jarvis", "jarvi", "javis", "jarves", "jarbas")
WAKE_PROMPT = "Palavra de ativação: Olá Jarvis. Oi Jarvis. Ei Jarvis."

log = logging.getLogger("jarvis.wake")


def setup_logging() -> None:
    handler = RotatingFileHandler(
        config.LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.addHandler(logging.StreamHandler(sys.stderr))
    log.setLevel(logging.INFO)


def app_running() -> bool:
    """True quando o aplicativo de terminal está aberto (segurando o lock)."""
    if not config.LOCK_PATH.exists():
        return False
    try:
        fd = os.open(config.LOCK_PATH, os.O_RDWR)
    except OSError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def open_terminal() -> subprocess.Popen | None:
    runner = ROOT / "run.sh"
    command = f"exec '{runner}'"
    candidates = [
        ["gnome-terminal", "--title=JARVIS", "--", "bash", "-lc", command],
        ["x-terminal-emulator", "-T", "JARVIS", "-e", "bash", "-lc", command],
        ["konsole", "-p", "tabtitle=JARVIS", "-e", "bash", "-lc", command],
        ["xterm", "-T", "JARVIS", "-e", "bash", "-lc", command],
    ]
    for argv in candidates:
        if shutil.which(argv[0]):
            try:
                proc = subprocess.Popen(argv, start_new_session=True)
                log.info("terminal aberto via %s (pid %s)", argv[0], proc.pid)
                return proc
            except Exception as exc:
                log.warning("falha com %s: %s", argv[0], exc)
    log.error("nenhum terminal disponível")
    return None


def matches_wake(text: str) -> bool:
    norm = normalize(text)
    if not norm:
        return False
    return any(v in norm for v in WAKE_VARIANTS)


class WakeListener:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.running = True
        self.last_trigger = 0.0
        self.stt = WhisperSTT(config.WAKE_MODEL, prompt=WAKE_PROMPT)

    def trigger(self, text: str) -> None:
        now = time.time()
        if now - self.last_trigger < 3.0:
            return
        self.last_trigger = now
        log.info("palavra-chave detectada: %r", text)
        if self.dry_run:
            print(f"[dry-run] palavra-chave: {text!r}", flush=True)
            return
        open_terminal()

    def run(self) -> None:
        mic: Mic | None = None
        try:
            while self.running:
                if app_running():
                    if mic is not None:
                        mic.close()
                        mic = None
                    if self.stt.loaded:
                        self.stt.unload()
                        log.info("assistente aberto: daemon em pausa")
                    time.sleep(0.7)
                    continue

                if mic is None:
                    try:
                        mic = Mic().open()
                    except Exception as exc:
                        log.error("microfone indisponível: %s", exc)
                        time.sleep(3)
                        continue
                    log.info("escutando a palavra-chave (%s)", config.WAKE_MODEL)
                    if not self.stt.loaded:
                        self.stt.load()

                audio = record_utterance(
                    mic, None, max_s=5.0, silence_s=0.7, start_timeout=0.5
                )
                if audio is None or audio.size < int(0.35 * config.MIC_SR):
                    continue

                text = self.stt.transcribe(audio)
                if matches_wake(text):
                    self.trigger(text)
                    time.sleep(1.2)
        finally:
            if mic is not None:
                mic.close()
        log.info("encerrando daemon")


def wav_test(path: str) -> int:
    """Transcreve um WAV e diz se a palavra-chave foi reconhecida."""
    import wave

    import numpy as np

    with wave.open(path, "rb") as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        data = w.readframes(w.getnframes())

    if width != 2:
        print("use WAV de 16 bits")
        return 2
    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    if sr != config.MIC_SR:
        n = int(round(audio.size * config.MIC_SR / sr))
        audio = np.interp(
            np.linspace(0, 1, n, endpoint=False),
            np.linspace(0, 1, audio.size, endpoint=False),
            audio,
        ).astype(np.float32)

    stt = WhisperSTT(config.WAKE_MODEL, prompt=WAKE_PROMPT)
    text = stt.transcribe(audio)
    print(f"transcrição: {text!r}")
    ok = matches_wake(text)
    print("PALAVRA-CHAVE DETECTADA" if ok else "não detectada")
    return 0 if ok else 1


def acquire_single_instance():
    """Evita dois daemons escutando ao mesmo tempo (autostart + manual)."""
    path = config.RUN / "wake.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    return fd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daemon da palavra-chave Jarvis")
    parser.add_argument("--dry-run", action="store_true", help="não abre terminal")
    parser.add_argument("--wav", help="testa um WAV em vez de escutar")
    args = parser.parse_args(argv)

    setup_logging()

    if args.wav:
        return wav_test(args.wav)

    lock = acquire_single_instance()
    if lock is None:
        log.info("já existe um daemon escutando; encerrando")
        return 0

    listener = WakeListener(dry_run=args.dry_run)

    def stop(*_):
        listener.running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    listener.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
