# Script Reference

## `search_audio_ui.py`

Purpose:
- Main user entry point.
- Accepts file path or raw query.
- Applies filename transformations and launches browser search.

Examples:
- File path mode:
  - `python3 search_audio_ui.py "/path/Artist - Title (Explicit).mp3"`
- Literal query mode:
  - `python3 search_audio_ui.py --literal-query "Artist - Title"`

Filename transformations:
- strip extension
- remove ` (Explicit)` / ` (explicit)`
- remove diacritics
- replace `_` with space
- split by ` - ` into artist/title
- truncate each side after `,`, `(`, `[`, `&`, `ft`, `feat`

Query cleanup:
- remove `DJ ` / `Dj ` / `dj `
- remove `Grupo ` / `grupo ` (case-insensitive after diacritic cleanup)
- remove standalone common contraction words such as `I'd`, `I'm`, `you're`, `don't`, `can't`, plus apostrophe-stripped forms such as `Id`, `Im`, `youre`, `dont`, `cant` (case-insensitive)

Useful flag:
- `--print-query` (debug transformed query)

## `browser_search_playwright.py`

Purpose:
- Browser automation engine.

Key flags:
- `--query`
- `--headed`
- `--ui-only`
- `--stay-open-seconds 0` (close window to end)
- `--storage-state <path>`
- `--audio-token <token>`
- `--downloads-dir <path>`
- `--username` / `--password` (override configured credentials)
- `--keychain-service <name>` (default: `djpoolrecords`)

Current behavior:
- Detects OutoftheBox audio module.
- When the saved session is logged out, opens the login page, fills the configured credentials, submits, and waits for authentication.
- Resolves credentials from flags, then `DJPOOL_USER` / `DJPOOL_PASS`, then macOS Keychain.
- Fast path for UI-only mode (no capture warm-up delay).
- In non-interactive mode, waits for manual login/challenge instead of requiring `input()`.
- Waits for audio widget readiness.
- Scrolls target field to top before entry.
- Verifies full query text before submit and retries if partial.
- Handles closed-window exits without traceback.
- Saves `--storage-state` only when authenticated (prevents clobbering good state with logged-out context).
- Stages downloads in temp dir and writes finalized files into downloads target.

## `configure_login.py`

Purpose:
- Prompts once for the DJPoolRecords username and password.
- Stores both values in macOS Keychain under the `djpoolrecords` service.
- Uses a hidden password prompt so the password is not placed in shell history.

## `query_search_field.py`

Purpose:
- Direct endpoint experimentation and diagnostics.

Useful features:
- `--raw-form`
- `--debug-file`
- `--pretty-print`
- `--probe-pagination`
- `--probe-advanced`

## `search_authenticated.py`

Purpose:
- Best-effort direct HTTP search with login/cookie support.

Limit:
- Vulnerable to Cloudflare/WAF challenge and nonce drift.
