#!/bin/zsh

SEARCH_SCRIPT="/Users/thompcha/Documents/Scripts/djpoolrecords/search_audio_ui.py"

if [[ ! -f "$SEARCH_SCRIPT" ]]; then
  echo "Missing script: $SEARCH_SCRIPT" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "No input file provided." >&2
  exit 1
fi

# First selected file path is searched using MP3/M4A artist/title tags.
exec /usr/bin/python3 "$SEARCH_SCRIPT" --print-query --query-from-tags "$1"
