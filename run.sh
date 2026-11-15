#!/usr/bin/env bash
# Abre o Jarvis no terminal atual e religa a escuta da palavra-chave.
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$ROOT"

case "${1:-}" in
    off|desligar|stop) exec "$ROOT/jarvis-ctl" off ;;
    status|estado)     exec "$ROOT/jarvis-ctl" status ;;
    wake)              exec "$ROOT/jarvis-ctl" wake ;;
esac

"$ROOT/jarvis-ctl" wake-open
exec .venv/bin/python -m jarvis.app "$@"
