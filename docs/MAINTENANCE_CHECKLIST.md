# Maintenance Checklist

## When Search Stops Working

1. Verify dependencies:
   - `python3 -m pip show playwright`
   - `python3 -m playwright --version`
2. Re-run in headed mode and observe UI behavior.
3. Confirm audio module still exists in homepage HTML:
   - `.wpcp-module.OutoftheBox[data-list='search']`
4. Confirm token/account values if hardcoded defaults are stale.
5. Refresh session state:
   - delete or replace `djpool_state.json`
   - login manually once
   - confirm logs do **not** show: `Skipping storage state save because browser context is not authenticated.` after successful login
6. If submit fails, inspect selector changes in page DOM.
7. If download naming regresses, verify staging/final download logic in `browser_search_playwright.py`.
8. For Automator/non-interactive runs, allow up to 5 minutes for manual login/challenge if prompted in browser.

## Regression Test Commands

- Wrapper path:
  - `python3 /Users/thompcha/Documents/Scripts/djpoolrecords/search_audio_ui.py --literal-query "drake"`
- Engine path:
  - `python3 /Users/thompcha/Documents/Scripts/djpoolrecords/browser_search_playwright.py --query "drake" --headed --ui-only --stay-open-seconds 0 --storage-state /Users/thompcha/Documents/Scripts/djpoolrecords/djpool_state.json`
- Download path override test:
  - `python3 /Users/thompcha/Documents/Scripts/djpoolrecords/browser_search_playwright.py --query "drake" --headed --ui-only --downloads-dir /Users/thompcha/Downloads`

## Security Hygiene

- Do not commit credentials.
- Rotate passwords shared in chats/logs.
- Treat copied cookie strings as sensitive.
