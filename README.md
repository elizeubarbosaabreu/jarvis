# JARVIS — assistente por voz no terminal

Diga **“Olá Jarvis”** e um terminal abre com um rosto ASCII animado que
espera seu comando por voz e responde falando.

Tudo roda local (voz e reconhecimento); só o texto da conversa vai para a
nuvem, e apenas quando você fala com ele.

## Instalação

Requisitos: Linux com GNOME (testado no Zorin OS 18 / GNOME 46, Wayland),
`uv`, `python3.12` e microfone.

```bash
git clone https://github.com/elizeubarbosaabreu/jarvis.git
cd jarvis
./install.sh
```

O `install.sh` cria o `.venv`, baixa a voz Piper e os modelos do Whisper,
instala a extensão do GNOME e liga a escuta da palavra-chave no login.
Depois da primeira instalação, saia e entre na sessão uma vez para o GNOME
carregar a extensão de controle de janelas.

A chave do modelo de linguagem é lida de `~/.local/share/opencode/auth.json`
(entrada `nvidia`) ou das variáveis `JARVIS_NVIDIA_KEY` / `NVIDIA_API_KEY`.
Sem chave, ele cai no Ollama local (`gemma3:1b`).

## Como usar

```bash
jarvis            # abre o assistente agora
```

- Fale normalmente; a pausa encerra o comando.
- Diga “sair”, “tchau” ou “até logo” para encerrar.
- Depois de 90 s sem fala ele entra em repouso e fecha (a palavra-chave volta a valer).
- `Ctrl+C` fecha a qualquer momento.

Para ligar a escuta contínua da palavra-chave:

```bash
./install.sh                  # instala tudo e o autostart do login
setsid nohup .venv/bin/python wake_daemon.py >/dev/null 2>&1 &
```

Desligar a escuta contínua:

```bash
pkill -f wake_daemon.py
rm ~/.config/autostart/jarvis-wake.desktop
```

## Comandos de desktop

| Você diz | O que acontece |
|---|---|
| “abrir o navegador”, “abre a calculadora” | abre o programa (ou traz para frente, se já estiver aberto) |
| “fechar o brave”, “fecha o terminal” | fecha o programa |
| “minimizar o brave” | minimiza a janela |
| “minimizar tudo” | minimiza todas as janelas |
| “mostrar a área de trabalho” | limpa a tela |
| “restaurar as janelas” | traz tudo de volta |
| “maximizar o brave” | maximiza |
| “o que está aberto?” | lista as janelas |
| “aumentar/diminuir o volume”, “volume em 30”, “silenciar” | áudio |

O controle de janelas usa uma extensão do GNOME (`jarvis-control@elizeu`) que
expõe um serviço DBus — é o caminho que funciona no **Wayland**. O GNOME só
varre extensões ao iniciar a sessão, então **saia e entre uma vez** depois de
instalar. Sem a extensão, abrir/fechar continuam funcionando (fechar encerra os
processos do programa); minimizar/maximizar ficam indisponíveis.

## Como funciona

| Peça | Papel |
|---|---|
| `wake_daemon.py` | fica ouvindo o microfone com VAD + Whisper `base` e abre o terminal ao ouvir “jarvis”. Pausa enquanto o assistente está aberto (lock em `run/jarvis.lock`). |
| `jarvis/app.py` | laço de conversa: grava o comando, transcreve, consulta o cérebro e fala. |
| `jarvis/face.py` | rosto ASCII com olhos que piscam, boca que acompanha a voz e equalizador. |
| `jarvis/audio.py` | microfone, detecção de fala e reprodução com nível de áudio. |
| `jarvis/stt.py` | faster-whisper `small` (int8, CPU), português. |
| `jarvis/tts.py` | Piper `pt_BR-faber-medium`, offline, com streaming por frase. |
| `jarvis/brain.py` | NVIDIA NIM (`nemotron-3.5-lightning`) com streaming; cai para o Ollama local se a rede falhar. Reflexos locais para horas, data e agradecimentos. |

## Configuração (variáveis de ambiente)

| Variável | Padrão | Para quê |
|---|---|---|
| `JARVIS_INPUT_DEVICE` | padrão do sistema | índice ou nome do microfone (`python -m sounddevice`) |
| `JARVIS_WHISPER` | `small` | modelo do assistente |
| `JARVIS_WAKE_WHISPER` | `base` | modelo da palavra-chave |
| `JARVIS_MODEL` | `nvidia/nemotron-3.5-lightning-30b-a3b` | modelo na nuvem |
| `JARVIS_OLLAMA_MODEL` | `gemma3:1b` | reserva offline |
| `JARVIS_IDLE_TIMEOUT` | `90` | segundos de silêncio até repousar (0 desliga) |
| `JARVIS_NVIDIA_KEY` | lê de `~/.local/share/opencode/auth.json` | chave da NVIDIA |

## Testes rápidos

```bash
.venv/bin/python -m jarvis.app --selftest        # voz -> texto -> resposta -> voz
.venv/bin/python wake_daemon.py --wav arquivo.wav  # a palavra-chave é reconhecida?
.venv/bin/python -m jarvis.app --demo-wav arquivo.wav  # conversa simulada
```

## Problemas comuns

- **Não ouve nada**: confira `JARVIS_INPUT_DEVICE` e o volume do microfone
  (`pactl get-source-volume @DEFAULT_SOURCE@`).
- **Resposta lenta**: o primeiro token vem da nuvem em ~0,7 s; sem rede ele usa
  o Ollama local (mais lento e mais simples). Instale outro modelo com
  `ollama pull qwen2.5:3b` e aponte `JARVIS_OLLAMA_MODEL`.
- **Abre dois terminais**: o daemon pausa ao ver `run/jarvis.lock`; se algo
  travou, apague o arquivo.
- **Logs**: `logs/jarvis.log`.
