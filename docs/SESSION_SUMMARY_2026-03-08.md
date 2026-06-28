# Session Summary (2026-03-08)

## Issue

Search flow started failing because browser sessions were no longer authenticated during runs, especially from Automator/non-interactive launches.

## Root Cause

1. Unauthenticated flow relied on `input()` pause, which can fail in non-interactive contexts.
2. Script could still save `--storage-state` after an unauthenticated run, overwriting a previously valid `djpool_state.json` with logged-out state.

## Fix Implemented

In `browser_search_playwright.py`:
- Added non-interactive auth wait path (`wait_for_auth_cookie`) that waits up to 5 minutes for manual login/challenge in the opened browser.
- Kept interactive path for terminal users (`press Enter` flow).
- Guarded storage-state writes so `djpool_state.json` is only saved when authenticated cookie is present.
- Added explicit log when state save is skipped due to unauthenticated context.

## Operational Impact

- Automator runs no longer fail immediately on stdin prompt when login is required.
- Valid session state is no longer clobbered by logged-out runs.
- Recovery is now: run headed once, complete login/challenge, close browser, then reuse saved state.
