#!/usr/bin/env bash
# Abre o Jarvis no terminal atual.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
exec .venv/bin/python -m jarvis.app "$@"
