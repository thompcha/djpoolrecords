# Architecture

## Layers

1. Input Layer
   - File path from Automator or query string from CLI.

2. Query Transformation Layer
   - Implemented in `search_audio_ui.py`.
   - Converts filenames into normalized search queries.

3. Execution Layer
   - `browser_search_playwright.py` drives a real browser session.
   - Auth session loaded from `djpool_state.json` when available.
   - UI-only fast path submits directly in page UI.

4. Target Layer
   - DJPoolRecords homepage audio search field.
   - Specifically `OutoftheBox` search module (not LetsBox).

5. Download Handling Layer
   - Browser download stream goes to temporary staging directory.
   - Final file is saved to configured downloads destination.
   - Staging artifacts are removed, preventing GUID junk files in Downloads.

## Why This Design

- Direct API/login approaches were fragile due to anti-bot protections.
- Browser-native flow matches real user behavior and plugin JS behavior.

## Data/State Files

- `djpool_state.json`: persisted auth/session cookies/storage for Playwright.
- Response/debug JSON files: optional outputs for diagnostics.

## Important Module Identifiers

From homepage markup:
- Audio module selector: `.wpcp-module.OutoftheBox[data-list='search']`
- Audio token default: `c91b8b53c4c2dfa5695a9f4ee991f2f4`

These may change if site owner reconfigures modules.
