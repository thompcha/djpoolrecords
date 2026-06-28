# Session Summary (2026-02-22)

## Objective

Automate DJPoolRecords search from local files, preserving the same behavior as typing into the authenticated homepage search form.

## Key Findings

1. Homepage includes multiple search modules:
   - Audio: `OutoftheBox` module (`data-token=c91b8b53c4c2dfa5695a9f4ee991f2f4`, `account_id=dbid:AADhlctnCxNQzW4RizhC1lOkBvCZMJ_XOTI`).
   - Video/other: multiple `LetsBox` modules.
2. Using `letsbox-get-filelist` returned video-heavy results.
3. Using `outofthebox-get-filelist` is required for audio search behavior.
4. Direct HTTP login flow was blocked by Cloudflare/WAF in scripted context.
5. Browser automation with Playwright worked reliably with persisted session state.

## Scripts Created/Updated

- Added `query_search_field.py` enhancements:
  - raw form mode
  - debug metadata output
  - pretty-print list output
  - pagination and advanced probes
- Added `search_authenticated.py`:
  - login/cookie support for direct requests
  - diagnostics for auth failures
- Added `browser_search_playwright.py`:
  - audio module targeting
  - auto login attempt
  - UI-only mode
  - close-window-to-exit
  - fast UI-only path for Automator
  - safe wait handling for clean close
  - robust full-query entry with retries/verification
  - scroll target field to top before input
  - staged download handling to prevent GUID junk files
- Added `search_audio_ui.py` wrapper:
  - accepts file path or literal query
  - applies filename-to-query transformation logic

## Final Preferred Flow

Use `search_audio_ui.py` from CLI or Automator. It launches Playwright in headed mode, targets OutoftheBox audio search, submits query in UI, downloads to final destination with clean names, and exits when browser closes.

## Known Constraints

- Requires Playwright + Chromium.
- Requires valid authenticated browser state (`djpool_state.json`) or manual login/challenge completion.
- Endpoint nonces rotate; direct HTTP route can break unexpectedly.
