# Automator Setup

## Recommended Automator Action

- Action: `Run Shell Script`
- Shell: `/bin/zsh`
- Pass input: `as arguments`

Script:

```zsh
#!/bin/zsh

APP_DIR="$HOME/Documents/Scripts/djpoolrecords"
PYTHON="$APP_DIR/.venv/bin/python"
SEARCH_SCRIPT="$APP_DIR/search_audio_ui.py"

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing venv Python: $PYTHON" >&2
  exit 1
fi

if [[ ! -f "$SEARCH_SCRIPT" ]]; then
  echo "Missing script: $SEARCH_SCRIPT" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "No input file provided." >&2
  exit 1
fi

exec "$PYTHON" "$SEARCH_SCRIPT" --print-query "$1"
```

Notes:
- `--print-query` is optional; useful while validating transformations.
- Add `--query-from-tags` before `"$1"` to search from MP3/M4A artist/title tags instead of the filename:
  - `exec "$PYTHON" "$SEARCH_SCRIPT" --print-query --query-from-tags "$1"`
- Automator now benefits from the fast UI-only path in Playwright.
- Browser close ends script cleanly (no Enter prompt).

## Automatic Login

Store the login in macOS Keychain once. The password prompt is hidden:

```zsh
cd "$HOME/Documents/Scripts/djpoolrecords"
source .venv/bin/activate
python configure_login.py
```

When the saved browser session is no longer authenticated, the app opens the login
page, fills these credentials, submits the form, and refreshes `djpool_state.json`.

For a terminal-only alternative, set `DJPOOL_USER` and `DJPOOL_PASS` in the
environment before launching the app.
