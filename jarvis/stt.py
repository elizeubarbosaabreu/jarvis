"""Reconhecimento de fala (faster-whisper, CPU)."""
from __future__ import annotations

import re

import numpy as np

from . import config

_HALLUCINATION = re.compile(
    r"^(um,? dois,? três|legendas? pela comunidade|obrigado por assistir|"
    r"inscreva-se|até a próxima|tchau tchau)\b",
    re.IGNORECASE,
)

PROMPT = (
    "Comandos em português do Brasil para o Jarvis: olá Jarvis, que horas são, "
    "que dia é hoje, tocar música, abrir o navegador, obrigado, até logo."
)


class WhisperSTT:
    def __init__(self, model_name: str = config.WHISPER_MODEL, prompt: str = PROMPT):
        self.model_name = model_name
        self.prompt = prompt
        self._model = None

    def load(self) -> None:
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_name,
                device="cpu",
                compute_type="int8",
                download_root=str(config.MODELS),
                cpu_threads=4,
            )

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def unload(self) -> None:
        import gc

        self._model = None
        gc.collect()

    def transcribe(self, audio: np.ndarray, sr: int = config.MIC_SR) -> str:
        self.load()
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        segments, _info = self._model.transcribe(
            audio,
            language="pt",
            task="transcribe",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
            initial_prompt=self.prompt,
            temperature=0.0,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
        )
        parts = []
        for seg in segments:
            if seg.no_speech_prob > 0.6 and seg.avg_logprob < -0.7:
                continue
            text = seg.text.strip()
            if text and not _HALLUCINATION.search(text):
                parts.append(text)
        return " ".join(parts).strip()
