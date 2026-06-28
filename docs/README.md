# DJPoolRecords Automation Docs

This folder documents the current automation stack for searching DJPoolRecords audio results.

## Quick Start

1. Install the app dependencies:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
   - `python -m pip install --upgrade pip`
   - `python -m pip install -r requirements.txt`
   - `python -m playwright install chromium`
2. Run one-argument audio UI search from a file:
   - `python search_audio_ui.py "/path/to/file.mp3"`
3. Run a literal query:
   - `python search_audio_ui.py --literal-query "artist - title"`

## GitHub Install on Another Mac

Create a private GitHub repository for this folder, then push the local repo.
Local browser state, debug responses, caches, virtual environments, and saved
site captures are excluded by `.gitignore`.

On the second Mac:

```zsh
mkdir -p ~/Documents/Scripts
cd ~/Documents/Scripts
git clone git@github.com:<your-github-user>/djpoolrecords.git
cd djpoolrecords

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
python configure_login.py
```

Test the install:

```zsh
source ~/Documents/Scripts/djpoolrecords/.venv/bin/activate
python ~/Documents/Scripts/djpoolrecords/search_audio_ui.py --literal-query "Drake - One Dance"
```

The first run may require browser login or challenge handling. After successful
authentication, the app creates a new local `djpool_state.json`; do not commit
or copy that file between Macs.

## Current Stable Behavior

- Targets **audio** widget only (`OutoftheBox`), not LetsBox/video widgets.
- UI-only mode is optimized (no slow pre-capture wait path).
- Script exits cleanly when browser window is closed.
- If unauthenticated in non-interactive runs (Automator), script waits for manual login instead of crashing on stdin prompt.
- Storage state is only saved when authenticated, preventing logged-out state from overwriting `djpool_state.json`.
- Query entry is resilient: waits for widget readiness, retries, verifies full text before submit.
- Search field is scrolled to top before typing.
- Downloads are staged to a temp folder, then saved to final Downloads path to avoid GUID garbage files.

## Core Scripts

- `browser_search_playwright.py`: browser automation engine (audio-module aware).
- `search_audio_ui.py`: wrapper that transforms filename -> query and launches browser search.
- `query_search_field.py`: direct AJAX querying utility with debugging/probing tools.
- `search_authenticated.py`: HTTP login/cookie-based request runner (best-effort, Cloudflare-sensitive).

## Why Browser Automation Is Primary

Direct login/API requests were blocked/inconsistent due to Cloudflare/WAF and rotating session nonces. Browser automation using a real authenticated session is the reliable path.

## Docs Index

- `docs/SESSION_SUMMARY_2026-03-08.md`
- `docs/SESSION_SUMMARY_2026-02-22.md`
- `docs/ARCHITECTURE.md`
- `docs/SCRIPT_REFERENCE.md`
- `docs/AUTOMATOR_SETUP.md`
- `docs/TROUBLESHOOTING.md`
- `docs/MAINTENANCE_CHECKLIST.md`
