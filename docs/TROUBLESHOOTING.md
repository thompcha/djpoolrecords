# Troubleshooting

## Slow in Automator, fast in terminal

Cause:
- Earlier versions waited through capture logic even in UI-only mode.

Fix status:
- UI-only fast path implemented in `browser_search_playwright.py`.

## Query partially entered or not submitted

Potential causes:
- Widget not initialized yet.
- Input listener missed early keystrokes.

Fix status:
- Waits for audio widget readiness.
- Scrolls input to top before entry.
- Retries entry and verifies full input value before submit.
- Falls back to `fill + input/change` events when needed.

## Traceback on browser close (`TargetClosedError`)

Cause:
- Waiting on page after user closed window.

Fix status:
- Safe wait wrapper catches closed-target situations and exits cleanly.

## Download saves with GUID junk filename in Downloads

Cause:
- Browser created raw artifact in final downloads location.

Fix status:
- Downloads now stage in temp folder, then save final named file to destination.

## Login/auth problems

- Configure credentials in macOS Keychain as described in `AUTOMATOR_SETUP.md`.
- If state is stale, the app automatically opens and submits the login page.
- CAPTCHA or other interactive challenges still require manual completion.
- Save/refresh `djpool_state.json`.
- Direct HTTP scripts may still fail under WAF constraints.

## `Page.goto: net::ERR_ABORTED; maybe frame was detached?`

Cause:
- DJPoolRecords can redirect or reattach the main frame during initial homepage load or challenge flow.
- Older navigation path assumed a stable `domcontentloaded` event and could fail immediately in Automator.

Fix status:
- Homepage/login navigations now retry automatically when Playwright reports `ERR_ABORTED`, frame-detached, or interrupted-navigation errors.

Recovery:
- Re-run the same Automator action.
- If the site presents a login or challenge page, complete it in the opened browser window and let the script continue.

## Not authenticated in Automator and script fails early

Cause:
- Older flow used `input()` after opening browser; non-interactive runs can fail immediately.
- Logged-out runs could overwrite `djpool_state.json`, making later runs start logged out.

Fix status:
- Non-interactive mode now waits up to 5 minutes for manual login in opened browser.
- Storage state is only written when authenticated cookie is present.

Recovery:
- Run once in headed mode and complete login/challenge.
- Close browser after confirming search UI works; state is saved automatically when authenticated.
- If needed, delete stale `djpool_state.json` and repeat.

## Wrong result type (video vs audio)

- Ensure OutoftheBox audio module is used.
- Avoid LetsBox token/action for audio workflow.
