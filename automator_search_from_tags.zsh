#!/bin/zsh

SEARCH_SCRIPT="/Users/thompcha/Documents/Scripts/djpoolrecords/search_audio_ui.py"
PYTHON="/Users/thompcha/Documents/Scripts/djpoolrecords/.venv/bin/python"

if [[ ! -f "$SEARCH_SCRIPT" ]]; then
  echo "Missing script: $SEARCH_SCRIPT" >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing virtual-environment Python: $PYTHON" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "No input file provided." >&2
  exit 1
fi

exec "$PYTHON" "$SEARCH_SCRIPT" --print-query --query-from-tags "$1"