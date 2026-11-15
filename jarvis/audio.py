"""Microfone, detecção de fala e reprodução com nível de áudio."""
from __future__ import annotations

import collections
import queue
import time

import numpy as np
import sounddevice as sd

from . import config


def _rms_db(frame: np.ndarray) -> float:
    """Nível em dBFS de um quadro int16."""
    x = frame.astype(np.float32) / 32768.0
    return float(20.0 * np.log10(float(np.sqrt(np.mean(x * x))) + 1e-9))


def level_to_unit(db: float) -> float:
    """dBFS -> 0..1 para animar o rosto."""
    return float(min(1.0, max(0.0, (db + 52.0) / 42.0)))


class Mic:
    """Fluxo contínuo de microfone em int16 mono 16 kHz."""

    def __init__(
        self,
        sr: int = config.MIC_SR,
        block: int = config.MIC_BLOCK,
        device=config.INPUT_DEVICE,
    ):
        if isinstance(device, str) and device.isdigit():
            device = int(device)
        self.device = device
        self.noise_db = -58.0
        self.sr = sr
        self.block = block
        self.queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=400)
        self.stream: sd.InputStream | None = None
        self.overflows = 0

    def _callback(self, indata, frames, time_info, status):
        if status:
            self.overflows += 1
        try:
            self.queue.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass

    def open(self) -> "Mic":
        self.stream = sd.InputStream(
            samplerate=self.sr,
            channels=1,
            dtype="int16",
            blocksize=self.block,
            device=self.device,
            callback=self._callback,
        )
        self.stream.start()
        self.calibrate()
        return self

    def calibrate(self, seconds: float = 0.6) -> None:
        """Mede o ruído de fundo para o detector de fala."""
        self.flush()
        values: list[float] = []
        t0 = time.time()
        while time.time() - t0 < seconds:
            frame = self.read(0.2)
            if frame is not None:
                values.append(_rms_db(frame))
        if values:
            self.noise_db = float(np.median(values))
        self.flush()

    def close(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            finally:
                self.stream = None

    def __enter__(self) -> "Mic":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    def read(self, timeout: float = 0.5) -> np.ndarray | None:
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def flush(self) -> None:
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                return


def record_utterance(
    mic: Mic,
    state=None,
    *,
    max_s: float = config.MAX_UTTERANCE_S,
    silence_s: float = config.SILENCE_S,
    start_timeout: float = config.START_TIMEOUT_S,
    preroll_s: float = config.PREROLL_S,
) -> np.ndarray | None:
    """Grava até o fim da fala. Devolve float32 mono ou None se ninguém falou."""
    sr, block = mic.sr, mic.block
    preroll: collections.deque[np.ndarray] = collections.deque(
        maxlen=max(1, int(preroll_s * sr / block))
    )
    frames: list[np.ndarray] = []
    noise = getattr(mic, "noise_db", -58.0)
    voiced = 0
    started = False
    t0 = time.time()
    last_voice = t0
    peak = 0.0
    max_db = -100.0

    while True:
        frame = mic.read(0.5)
        if frame is None:
            if not started and time.time() - t0 > start_timeout:
                return None
            continue

        db = _rms_db(frame)
        threshold = max(-46.0, noise + 8.5)
        speech = db > threshold
        max_db = max(max_db, db)
        if state is not None:
            state.level = level_to_unit(db)
            peak = max(peak, state.level)

        if not started:
            preroll.append(frame)
            if not speech:
                noise = 0.98 * noise + 0.02 * db
            voiced = voiced + 1 if speech else 0
            if voiced >= 3 and max_db > max(-42.0, threshold + 2.0):
                started = True
                frames = list(preroll)
                preroll.clear()
                last_voice = time.time()
            elif time.time() - t0 > start_timeout:
                return None
        else:
            frames.append(frame)
            if speech:
                last_voice = time.time()
            if time.time() - last_voice > silence_s:
                break

        if time.time() - t0 > max_s:
            break

    if state is not None:
        state.level = 0.0
    mic.noise_db = noise
    if not frames:
        return None
    audio = np.concatenate(frames).astype(np.float32) / 32768.0
    if audio.size < int(0.2 * sr):
        return None
    return audio


def load_wav(path: str, target_sr: int = config.MIC_SR) -> np.ndarray:
    """Lê um WAV (qualquer taxa/canais) e devolve float32 mono na taxa alvo."""
    import wave

    with wave.open(path, "rb") as w:
        sr, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        data = w.readframes(w.getnframes())
    if width == 2:
        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        audio = np.frombuffer(data, dtype=np.int32).astype(np.float32) / 2**31
    else:
        raise ValueError(f"WAV de {width * 8} bits não suportado")
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    return _resample(audio, sr, target_sr)


def _resample(audio: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or audio.size == 0:
        return audio
    n = int(round(audio.size * dst / src))
    x_old = np.linspace(0.0, 1.0, audio.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def play(
    audio: np.ndarray,
    sr: int,
    on_level=None,
    stop_flag=None,
    block_s: float = 0.03,
) -> None:
    """Toca áudio float32 mono, informando o nível para animar a boca."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0:
        return

    # pequeno fade para evitar estalos
    fade = min(int(0.008 * sr), audio.size // 2)
    if fade > 0:
        audio[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        audio[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)

    try:
        stream = sd.OutputStream(samplerate=sr, channels=1, dtype="float32")
    except Exception:
        audio = _resample(audio, sr, 48000)
        sr = 48000
        stream = sd.OutputStream(samplerate=sr, channels=1, dtype="float32")

    step = max(1, int(block_s * sr))
    levels = [
        float(np.sqrt(np.mean(audio[i : i + step] ** 2)) + 1e-9)
        for i in range(0, audio.size, step)
    ]
    peak = max(levels) if levels else 1.0

    with stream:
        for idx, i in enumerate(range(0, audio.size, step)):
            if stop_flag is not None and stop_flag.is_set():
                break
            chunk = audio[i : i + step]
            if on_level is not None:
                on_level(min(1.0, (levels[idx] / peak) ** 0.75))
            stream.write(chunk.reshape(-1, 1))
    if on_level is not None:
        on_level(0.0)
