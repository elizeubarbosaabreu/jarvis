"""Configuração central do Jarvis."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
VOICES = ROOT / "voices"
RUN = ROOT / "run"
LOGS = ROOT / "logs"

for _d in (RUN, LOGS):
    _d.mkdir(parents=True, exist_ok=True)

# --- áudio ---------------------------------------------------------------
INPUT_DEVICE = os.getenv("JARVIS_INPUT_DEVICE") or None

MIC_SR = 16000          # taxa usada por Whisper/Vosk
MIC_BLOCK = 512         # 32 ms por quadro
SILENCE_S = 0.85        # silêncio que encerra o comando
MAX_UTTERANCE_S = 14.0  # duração máxima de um comando
START_TIMEOUT_S = 7.0   # espera máxima pela fala após abrir o microfone
PREROLL_S = 0.5        # áudio guardado antes do início da fala

# --- modelos -------------------------------------------------------------
WHISPER_MODEL = os.getenv("JARVIS_WHISPER", "small")
WAKE_MODEL = os.getenv("JARVIS_WAKE_WHISPER", "base")
PIPER_VOICE = VOICES / "pt_BR-faber-medium.onnx"

# --- cérebro -------------------------------------------------------------
NVIDIA_MODEL = os.getenv("JARVIS_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
OLLAMA_MODEL = os.getenv("JARVIS_OLLAMA_MODEL", "gemma3:1b")
OLLAMA_URL = os.getenv("JARVIS_OLLAMA_URL", "http://localhost:11434")
LLM_TIMEOUT_S = float(os.getenv("JARVIS_LLM_TIMEOUT", "40"))

SYSTEM_PROMPT = (
    "Você é JARVIS, o assistente pessoal de voz do senhor. Fale português do Brasil. "
    "Suas respostas são faladas em voz alta: escreva apenas texto puro, sem markdown, "
    "sem listas, sem emojis, sem endereços de site. Seja conciso e direto: uma a três "
    "frases curtas, a menos que peçam detalhes. Trate o usuário por 'senhor'. "
    "Tom calmo, leal e levemente espirituoso, como um mordomo muito competente. "
    "Você também controla o computador do senhor: abrir e fechar programas, "
    "minimizar e maximizar janelas, mostrar a área de trabalho, ajustar o volume "
    "e abrir vídeos e buscas no YouTube pelo navegador. "
    "Nunca diga que é um modelo de linguagem; você é o JARVIS."
)

# --- sessão --------------------------------------------------------------
LOCK_PATH = RUN / "jarvis.lock"
LOG_PATH = LOGS / "jarvis.log"

IDLE_TIMEOUT_S = float(os.getenv("JARVIS_IDLE_TIMEOUT", "90"))

EXIT_WORDS = (
    "sair", "tchau", "ate logo", "até logo", "encerrar", "encerra",
    "desligar", "desliga", "boa noite", "pode descansar", "descansar",
)
