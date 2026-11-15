#!/usr/bin/env bash
# Instala (ou reinstala) o Jarvis de forma idempotente.
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$ROOT"

AUTOSTART=1
for arg in "$@"; do
  case "$arg" in
    --no-autostart) AUTOSTART=0 ;;
    *) echo "opção desconhecida: $arg" >&2; exit 1 ;;
  esac
done

echo "==> ambiente Python (.venv)"
if [ ! -x .venv/bin/python ]; then
  uv venv --python 3.12 .venv
fi
uv pip install --python .venv/bin/python -r requirements.txt

echo "==> voz Piper (pt-BR)"
mkdir -p voices
if [ ! -f voices/pt_BR-faber-medium.onnx ]; then
  .venv/bin/python -m piper.download_voices pt_BR-faber-medium --data-dir voices
fi

echo "==> modelos Whisper (pequeno para ouvir, médio para conversar)"
.venv/bin/python - <<'PY'
from faster_whisper import WhisperModel
for name in ("base", "small"):
    WhisperModel(name, device="cpu", compute_type="int8", download_root="models")
print("modelos prontos")
PY

echo "==> extensão do GNOME (controle de janelas no Wayland)"
EXT_UUID="jarvis-control@elizeu"
EXT_SRC="$ROOT/gnome-extension/$EXT_UUID"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"
if [ -d "$EXT_SRC" ]; then
  mkdir -p "$HOME/.local/share/gnome-shell/extensions"
  rm -rf "$EXT_DIR"
  cp -r "$EXT_SRC" "$EXT_DIR"
  python3 - "$EXT_UUID" <<'PY'
import ast, subprocess, sys
uuid = sys.argv[1]
try:
    cur = subprocess.run(["gsettings", "get", "org.gnome.shell", "enabled-extensions"],
                         capture_output=True, text=True).stdout.strip()
    lst = ast.literal_eval(cur) if cur else []
    if uuid not in lst:
        lst.append(uuid)
        val = "[" + ", ".join(f"'{x}'" for x in lst) + "]"
        subprocess.run(["gsettings", "set", "org.gnome.shell", "enabled-extensions", val], check=True)
except Exception as exc:
    print("aviso: não consegui habilitar a extensão automaticamente:", exc)
PY
fi

chmod +x run.sh wake_daemon.py

echo "==> comando 'jarvis' em ~/.local/bin"
mkdir -p "$HOME/.local/bin"
ln -sf "$ROOT/run.sh" "$HOME/.local/bin/jarvis"

if [ "$AUTOSTART" = 1 ]; then
  echo "==> autostart da palavra-chave"
  mkdir -p "$HOME/.config/autostart" "$HOME/.local/share/applications"
  sed "s#/home/elizeu/jarvis#$ROOT#g" jarvis-wake.desktop \
    > "$HOME/.config/autostart/jarvis-wake.desktop"
  mkdir -p "$HOME/.config/systemd/user"
  sed "s#/home/elizeu/jarvis#$ROOT#g" jarvis-wake.service \
    > "$HOME/.config/systemd/user/jarvis-wake.service"
  cat > "$HOME/.local/share/applications/jarvis.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=JARVIS
Comment=Assistente por voz com rosto ASCII
Exec=$ROOT/run.sh
Path=$ROOT
Terminal=true
Icon=utilities-terminal
Categories=Utility;
EOF
  command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications" || true

  echo "==> lançador na área de trabalho (botão para abrir)"
  DESKTOP_DIR="$HOME/Desktop"
  [ -d "$DESKTOP_DIR" ] || DESKTOP_DIR="$HOME/Área de trabalho"
  if [ -d "$DESKTOP_DIR" ]; then
    cat > "$DESKTOP_DIR/jarvis.desktop" <<DESKEOF
[Desktop Entry]
Type=Application
Name=JARVIS
Comment=Assistente por voz com rosto ASCII
Exec=bash -lc '$ROOT/run.sh'
Path=$ROOT
Terminal=true
Icon=utilities-terminal
Categories=Utility;
DESKEOF
    chmod +x "$DESKTOP_DIR/jarvis.desktop" 2>/dev/null || true
    command -v update-desktop-database >/dev/null && update-desktop-database "$DESKTOP_DIR" || true
  fi
fi

echo
echo "Pronto."
echo "  falar 'Olá Jarvis'  -> abre o terminal"
echo "  jarvis              -> abre manualmente"
echo "  botão JARVIS na área de trabalho  -> abre pelo menu/launcher"
echo "  desligar o jarvis (por voz)  -> encerra tudo até ser chamado novamente"
echo "  desligar autostart  -> rm ~/.config/autostart/jarvis-wake.desktop"
echo
echo "Se acabou de instalar: saia e entre na sessão uma vez para o GNOME"
echo "carregar a extensão de controle de janelas (minimizar/maximizar/área de trabalho)."
