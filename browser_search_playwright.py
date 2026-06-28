#!/usr/bin/env python3
"""Run DJPoolRecords search through a real browser session using Playwright."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qsl

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except Exception as exc:  # pragma: no cover
    print(f"Missing dependency: playwright ({exc})", file=sys.stderr)
    print("Install with: pip install playwright && python -m playwright install chromium", file=sys.stderr)
    raise SystemExit(2)

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

BASE_URL = "https://djpoolrecords.com/"
AJAX_PATH = "/wp-admin/admin-ajax.php"
TARGET_AUDIO_ACTION = "outofthebox-get-filelist"
DEFAULT_LOGIN_URL = "https://djpoolrecords.com/djpoolrecords-user-login/"
DEFAULT_KEYCHAIN_SERVICE = "djpoolrecords"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Browser-automated DJPoolRecords search via captured AJAX template.")
    p.add_argument("--query", required=True, help="Search query")
    p.add_argument("--output", default="response_browser.json", help="Output response path")
    p.add_argument("--debug-file", default="", help="Write debug metadata JSON")
    p.add_argument("--storage-state", default="", help="Path to Playwright storage state JSON")
    p.add_argument("--audio-token", default="", help="OutoftheBox audio module token override")
    p.add_argument("--login-url", default=DEFAULT_LOGIN_URL, help="Login page URL")
    p.add_argument("--username", default="", help="Login username/email")
    p.add_argument("--password", default="", help="Login password")
    p.add_argument(
        "--keychain-service",
        default=DEFAULT_KEYCHAIN_SERVICE,
        help="macOS Keychain service containing username and password items",
    )
    p.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    p.add_argument("--capture-timeout", type=int, default=40, help="Seconds to wait for AJAX template capture")
    p.add_argument("--pretty-print", action="store_true", help="Pretty-print returned files")
    p.add_argument("--pretty-limit", type=int, default=20, help="Pretty-print row limit (0 = all)")
    p.add_argument(
        "--downloads-dir",
        default=str(Path.home() / "Downloads"),
        help="Directory where browser-triggered downloads are saved",
    )
    p.add_argument(
        "--ui-only",
        action="store_true",
        help="Type query into the site search field and show UI results without direct AJAX replay",
    )
    p.add_argument(
        "--stay-open-seconds",
        type=int,
        default=120,
        help="When --ui-only is used, keep browser open this many seconds (0 = wait for Enter)",
    )
    return p.parse_args()


def is_matching_ajax(url: str, post_data: str, action: str, token: str) -> bool:
    if AJAX_PATH not in url:
        return False
    if not post_data:
        return False
    form = dict(parse_qsl(post_data, keep_blank_values=True))
    if form.get("action", "") != action:
        return False
    if token and form.get("listtoken", "") != token:
        return False
    return True


def pretty_print_files(raw: bytes, limit: int) -> None:
    if BeautifulSoup is None:
        print("Pretty print skipped: bs4 not installed.", file=sys.stderr)
        return

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        print(f"Pretty print skipped: invalid JSON ({exc})", file=sys.stderr)
        return

    html = payload.get("html")
    if not isinstance(html, str):
        print("Pretty print skipped: response has no html field.", file=sys.stderr)
        return

    soup = BeautifulSoup(html, "html.parser")
    entries = soup.select(".entry.file")
    if not entries:
        print("No file entries found.")
        return

    rows = []
    for entry in entries:
        name_node = entry.select_one(".entry-info-name")
        size_node = entry.select_one(".entry-info-size")
        dl_node = entry.select_one("a.entry_action_download")
        name = name_node.get_text(" ", strip=True) if name_node else (entry.get("data-name") or "")
        size = size_node.get_text(" ", strip=True) if size_node else ""
        link = dl_node.get("href") if dl_node else ""
        rows.append((name, size, link))

    if limit > 0:
        rows = rows[:limit]

    print(f"filescount={payload.get('filescount')} rows_printed={len(rows)}")
    for idx, (name, size, link) in enumerate(rows, 1):
        print(f"{idx:>3}. {name} [{size}]")
        if link:
            print(f"     {link}")


def has_wp_login_cookie(context) -> bool:
    try:
        cookies = context.cookies()
    except Exception:
        return False
    return any(c.get("name", "").startswith("wordpress_logged_in_") for c in cookies)


def wait_for_auth_cookie(page, context, timeout_seconds: int = 300) -> bool:
    deadline = time.time() + max(1, timeout_seconds)
    while time.time() < deadline:
        if has_wp_login_cookie(context):
            return True
        if not safe_wait(page, 1000):
            return False
    return has_wp_login_cookie(context)


def read_keychain_secret(service: str, account: str) -> str:
    if sys.platform != "darwin" or not service:
        return ""
    try:
        result = subprocess.run(
            [
                "/usr/bin/security",
                "find-generic-password",
                "-s",
                service,
                "-a",
                account,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.rstrip("\r\n")


def resolve_login_credentials(args: argparse.Namespace) -> tuple[str, str]:
    username = args.username or os.environ.get("DJPOOL_USER", "")
    password = args.password or os.environ.get("DJPOOL_PASS", "")

    if not username:
        username = read_keychain_secret(args.keychain_service, "username")
    if not password:
        password = read_keychain_secret(args.keychain_service, "password")
    return username, password


def detect_audio_module(page, timeout_ms: int = 15000) -> tuple[str, str]:
    deadline = time.time() + max(1, timeout_ms) / 1000
    last_exc: Exception | None = None
    while time.time() < deadline:
        try:
            page.wait_for_selector(
                ".wpcp-module.OutoftheBox[data-list='search']",
                timeout=1000,
                state="attached",
            )
            data = page.evaluate(
                """
                () => {
                  const el = document.querySelector(".wpcp-module.OutoftheBox[data-list='search']");
                  if (!el) return { token: "", module_id: "" };
                  return {
                    token: el.getAttribute("data-token") || "",
                    module_id: el.getAttribute("id") || "",
                  };
                }
                """
            )
            return data.get("token", ""), data.get("module_id", "")
        except Exception as exc:
            last_exc = exc
            if page.is_closed() or not is_retryable_navigation_error(exc):
                raise
            if not safe_wait(page, 300):
                break
    if last_exc is not None and not is_retryable_navigation_error(last_exc):
        raise last_exc
    return "", ""


def safe_wait(page, ms: int) -> bool:
    try:
        if page.is_closed():
            return False
        page.wait_for_timeout(ms)
        return True
    except Exception:
        return False


def is_retryable_navigation_error(exc: Exception) -> bool:
    text = str(exc)
    markers = [
        "ERR_ABORTED",
        "Execution context was destroyed",
        "frame was detached",
        "Frame was detached",
        "Navigation interrupted",
        "most likely because of a navigation",
    ]
    return any(marker in text for marker in markers)


def goto_with_retry(page, url: str, attempts: int = 3) -> None:
    last_exc: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            page.goto(url, wait_until="domcontentloaded")
            return
        except Exception as exc:
            last_exc = exc
            if not is_retryable_navigation_error(exc) or attempt >= attempts or page.is_closed():
                raise
            print(f"Navigation aborted while loading {url}; retrying ({attempt}/{attempts})...")
            if not safe_wait(page, 800 * attempt):
                break
    if last_exc is not None:
        raise last_exc


def reload_with_retry(page, attempts: int = 3) -> None:
    last_exc: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            page.reload(wait_until="domcontentloaded")
            return
        except Exception as exc:
            last_exc = exc
            if not is_retryable_navigation_error(exc) or attempt >= attempts or page.is_closed():
                raise
            print(f"Navigation aborted while reloading page; retrying ({attempt}/{attempts})...")
            if not safe_wait(page, 800 * attempt):
                break
    if last_exc is not None:
        raise last_exc


def wait_for_audio_ready(page, timeout_ms: int = 15000) -> bool:
    deadline = time.time() + max(1, timeout_ms) / 1000
    visible_input_seen_at: float | None = None
    last_exc: Exception | None = None

    while time.time() < deadline:
        try:
            ready_state = page.evaluate(
                """
                () => {
                  const module = document.querySelector(".wpcp-module.OutoftheBox[data-list='search']");
                  if (!module) return { attached: false, ready: false, visibleInput: false };
                  const input = module.querySelector("input[type='search'], input.search-input, input[name='q']");
                  const visibleInput = !!input && !input.disabled && !input.readOnly && (() => {
                    const rect = input.getBoundingClientRect();
                    const style = window.getComputedStyle(input);
                    return rect.width > 0 && rect.height > 0 &&
                      style.display !== "none" &&
                      style.visibility !== "hidden" &&
                      style.pointerEvents !== "none";
                  })();
                  return {
                    attached: true,
                    ready: visibleInput && !module.classList.contains("jsdisabled"),
                    visibleInput,
                  };
                }
                """
            )
            if ready_state.get("ready"):
                return True

            if ready_state.get("visibleInput"):
                if visible_input_seen_at is None:
                    visible_input_seen_at = time.time()
                elif time.time() - visible_input_seen_at >= 0.5:
                    return True
            else:
                visible_input_seen_at = None
        except Exception as exc:
            last_exc = exc
            if page.is_closed() or not is_retryable_navigation_error(exc):
                raise

        if not safe_wait(page, 150):
            return False

    if last_exc is not None and not is_retryable_navigation_error(last_exc):
        raise last_exc
    return False


def has_no_content_error(page) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=1000)
        return "No content received. Try to reload this page." in text
    except Exception:
        return False


def scroll_target_to_top(target) -> None:
    try:
        target.evaluate(
            """
            (el) => {
              el.scrollIntoView({ block: 'start', inline: 'nearest', behavior: 'instant' });
              const y = window.scrollY || window.pageYOffset || 0;
              if (y > 0) window.scrollTo(0, Math.max(0, y - 2));
            }
            """
        )
    except Exception:
        pass


def set_search_input_value(target, query: str) -> bool:
    try:
        target.fill(query)
        target.evaluate(
            """
            (el) => {
              el.dispatchEvent(new Event("input", { bubbles: true }));
              el.dispatchEvent(new Event("change", { bubbles: true }));
            }
            """
        )
        return (target.input_value() or "").strip() == query
    except Exception:
        return False


def apply_content_width_override(page) -> None:
    try:
        page.evaluate(
            """
            () => {
              const styleId = "djpool-widget-layout-override";
              let style = document.getElementById(styleId);
              if (!style) {
                style = document.createElement("style");
                style.id = styleId;
                document.head.appendChild(style);
              }
              style.textContent = `
                :root {
                  --djpool-player-buffer: 100px;
                }
                html,
                body {
                  width: 100vw !important;
                  height: 100vh !important;
                  overflow: hidden !important;
                }
                body[data-djpool-widget-only] {
                  margin: 0 !important;
                }
                body[data-djpool-widget-only] .main-container {
                  display: none !important;
                }
                [data-djpool-widget-root] {
                  position: fixed !important;
                  inset: 0 !important;
                  width: 100vw !important;
                  height: calc(100vh - var(--djpool-player-buffer)) !important;
                  max-width: 100vw !important;
                  max-height: calc(100vh - var(--djpool-player-buffer)) !important;
                  margin: 0 !important;
                  padding: 0 !important;
                  z-index: 1 !important;
                  overflow: hidden !important;
                }
                [data-djpool-widget-root] .wpcp-module.OutoftheBox {
                  display: block !important;
                  height: calc(100vh - var(--djpool-player-buffer)) !important;
                }
                [data-djpool-widget-root] .wpcp-browser-container {
                  display: flex !important;
                  width: 100vw !important;
                  max-width: 100vw !important;
                  height: calc(100vh - var(--djpool-player-buffer)) !important;
                  min-height: calc(100vh - var(--djpool-player-buffer)) !important;
                }
                [data-djpool-widget-root] .wpcp-browser-container-tree {
                  display: none !important;
                }
                [data-djpool-widget-root] .wpcp-browser-container-content {
                  display: flex !important;
                  flex-direction: column !important;
                  width: 100% !important;
                  height: 100% !important;
                  min-height: 0 !important;
                }
                [data-djpool-widget-root] .nav-header.OutoftheBox {
                  flex: 0 0 auto !important;
                }
                [data-djpool-widget-root] .wpcp-container-content {
                  display: flex !important;
                  flex: 1 1 auto !important;
                  flex-direction: column !important;
                  min-height: 0 !important;
                }
                #OutoftheBox .ajax-filelist,
                .OutoftheBox .ajax-filelist {
                  flex: 1 1 auto !important;
                  min-height: 0 !important;
                  max-height: none !important;
                  overflow-y: auto !important;
                  overscroll-behavior: contain !important;
                }
                #OutoftheBox .scroll-to-top,
                .OutoftheBox .scroll-to-top {
                  display: none !important;
                }
              `;
            }
            """
        )
    except Exception:
        pass


def focus_outofthebox_widget(page) -> None:
    try:
        page.evaluate(
            """
            () => {
              const root = document.querySelector(
                ".wpcp-container:has(.wpcp-module.OutoftheBox[data-list='search'])"
              );
              if (!root) return;
              if (root.parentElement !== document.body) {
                document.body.appendChild(root);
              }
              root.setAttribute("data-djpool-widget-root", "1");
              document.body.setAttribute("data-djpool-widget-only", "1");
            }
            """
        )
    except Exception:
        pass


def ensure_dark_mode(page, timeout_ms: int = 5000) -> None:
    try:
        already_active = page.evaluate(
            """
            () => {
              const html = document.documentElement;
              const body = document.body;
              return Boolean(
                html?.hasAttribute("data-wp-dark-mode-active") ||
                html?.classList.contains("wp-dark-mode-active") ||
                html?.classList.contains("drdt-dark-mode") ||
                body?.classList.contains("dark-mode")
              );
            }
            """
        )
        if already_active:
            return

        switch = page.locator(".wp-dark-mode-floating-switch .wp-dark-mode-switch").first
        switch.wait_for(state="visible", timeout=timeout_ms)
        switch.click()
        safe_wait(page, 400)
    except Exception:
        pass


def submit_query_in_ui(page, query: str, module_token: str = "", module_id: str = "") -> bool:
    # Common search input selectors used in WP plugin UIs.
    scoped_selectors = []
    if module_id:
        scoped_selectors.extend(
            [
                f"#{module_id} input[type='search']",
                f"#{module_id} input[name='query']",
                f"#{module_id} input[name='search']",
                f"#{module_id} input[placeholder*='Search' i]",
            ]
        )
    if module_token:
        scoped_selectors.extend(
            [
                f".wpcp-module.OutoftheBox[data-token='{module_token}'] input[type='search']",
                f".wpcp-module.OutoftheBox[data-token='{module_token}'] input[name='query']",
                f".wpcp-module.OutoftheBox[data-token='{module_token}'] input[name='search']",
            ]
        )

    selectors = scoped_selectors + [
        "input[type='search']",
        "input[name='query']",
        "input[name='search']",
        "input[placeholder*='Search' i]",
        "input[placeholder*='search' i]",
    ]

    def _try_submit_target(target) -> bool:
        for _ in range(4):
            try:
                if not target.is_visible() or not target.is_enabled() or not target.is_editable():
                    if not safe_wait(page, 200):
                        return False
                    continue

                scroll_target_to_top(target)
                target.click()
                # Ensure field is cleared and receives key events.
                target.press("Meta+a")
                target.press("Backspace")
                if not set_search_input_value(target, query):
                    target.press("Delete")

                entered = (target.input_value() or "").strip()
                if entered != query and set_search_input_value(target, query):
                    entered = (target.input_value() or "").strip()

                if entered != query:
                    if not safe_wait(page, 180):
                        return False
                    continue

                target.press("Enter")

                # Extra nudge: click nearby submit/magnifier if present.
                target.evaluate(
                    """
                    (el) => {
                      const root = el.closest('.wpcp-module.OutoftheBox') || el.closest('form') || el.parentElement;
                      if (!root) return;
                      const btn = root.querySelector(
                        "button[type='submit'], input[type='submit'], .promagnifier, .wpcp-search-button, .entry_action_search"
                      );
                      if (btn) btn.click();
                    }
                    """
                )
                return True
            except Exception:
                if not safe_wait(page, 180):
                    return False
                continue
        return False

    for sel in selectors:
        loc = page.locator(sel)
        count = loc.count()
        for i in range(count):
            target = loc.nth(i)
            if _try_submit_target(target):
                return True

    # Fallback: locate a likely visible text input via JS and submit Enter key.
    handle = page.evaluate_handle(
        """
        () => {
          const candidates = Array.from(document.querySelectorAll("input"));
          const usable = candidates.find((el) => {
            const type = (el.getAttribute("type") || "text").toLowerCase();
            if (!["text", "search"].includes(type)) return false;
            const style = window.getComputedStyle(el);
            const visible = style.display !== "none" && style.visibility !== "hidden" && el.offsetParent !== null;
            const hint = `${el.name || ""} ${el.placeholder || ""} ${el.id || ""}`.toLowerCase();
            return visible && (hint.includes("search") || hint.includes("query"));
          });
          return usable || null;
        }
        """
    )
    try:
        el = handle.as_element()
        if el is None:
            return False
        for _ in range(3):
            scroll_target_to_top(el)
            el.click()
            el.press("Meta+a")
            el.press("Backspace")
            entered = (el.input_value() or "").strip()
            if entered != query and set_search_input_value(el, query):
                entered = (el.input_value() or "").strip()
            if entered == query:
                el.press("Enter")
                return True
            if not safe_wait(page, 160):
                return False
        return False
    except Exception:
        return False


def try_auto_login(page, context, login_url: str, username: str, password: str) -> bool:
    if not username or not password:
        return False

    goto_with_retry(page, login_url)

    user_selectors = [
        "input[name='log']",
        "input[name='username']",
        "input[name='user_login']",
        "input[type='email']",
        "input#username",
    ]
    pass_selectors = [
        "input[name='pwd']",
        "input[name='password']",
        "input[type='password']",
        "input#password",
    ]
    submit_selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button[name='wp-submit']",
        "#wp-submit",
    ]

    user_filled = False
    pass_filled = False
    for sel in user_selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.fill(username)
            user_filled = True
            break
    for sel in pass_selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.fill(password)
            pass_filled = True
            break

    if not (user_filled and pass_filled):
        return False

    submitted = False
    for sel in submit_selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            loc.first.click()
            submitted = True
            break
    if not submitted:
        page.keyboard.press("Enter")

    wait_for_auth_cookie(page, context, timeout_seconds=20)
    return True


def load_home_page(page) -> None:
    goto_with_retry(page, BASE_URL)
    apply_content_width_override(page)
    focus_outofthebox_widget(page)
    ensure_dark_mode(page)


def main() -> int:
    args = parse_args()
    username, password = resolve_login_credentials(args)

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    downloads_dir = Path(args.downloads_dir).expanduser().resolve()
    downloads_dir.mkdir(parents=True, exist_ok=True)
    staging_downloads_dir = Path(tempfile.mkdtemp(prefix="djpool_playwright_dl_"))

    captured: dict[str, str] = {}
    capture_config = {"action": TARGET_AUDIO_ACTION, "token": args.audio_token}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not args.headed,
            downloads_path=str(staging_downloads_dir),
        )

        context_kwargs = {}
        if args.storage_state and Path(args.storage_state).expanduser().exists():
            context_kwargs["storage_state"] = str(Path(args.storage_state).expanduser().resolve())

        context = browser.new_context(accept_downloads=True, **context_kwargs)
        page = context.new_page()
        page.on("domcontentloaded", lambda: apply_content_width_override(page))

        def on_download(download):
            try:
                suggested = download.suggested_filename or "download.bin"
                candidate = downloads_dir / suggested
                if candidate.exists():
                    stem = candidate.stem
                    suffix = candidate.suffix
                    i = 1
                    while True:
                        alt = downloads_dir / f"{stem} ({i}){suffix}"
                        if not alt.exists():
                            candidate = alt
                            break
                        i += 1
                download.save_as(str(candidate))
                # Playwright may keep the original GUID-named artifact in downloads_path.
                # Remove it after saving the user-friendly copy.
                try:
                    src = download.path()
                    if src:
                        src_path = Path(src)
                        if src_path.exists() and src_path.resolve() != candidate.resolve():
                            src_path.unlink()
                except Exception:
                    pass
                print(f"Downloaded: {candidate}")
            except Exception as exc:
                print(f"Download handling failed: {exc}", file=sys.stderr)

        page.on("download", on_download)

        def on_request(req):
            if captured:
                return
            post_data = req.post_data or ""
            if is_matching_ajax(
                req.url,
                post_data,
                action=capture_config["action"],
                token=capture_config["token"],
            ):
                captured["url"] = req.url
                captured["post_data"] = post_data
                captured["method"] = req.method
                captured["headers_json"] = json.dumps(req.headers)

        page.on("request", on_request)

        load_home_page(page)

        login_attempted = False
        if not has_wp_login_cookie(context):
            login_attempted = try_auto_login(
                page,
                context,
                args.login_url,
                username,
                password,
            )
            load_home_page(page)
            if not has_wp_login_cookie(context):
                print("Not authenticated in browser context.")
                if login_attempted:
                    print("Auto-login attempted but session cookie was not set.")
                if sys.stdin.isatty():
                    print("Complete login/challenge in the opened browser window, then press Enter here.")
                    try:
                        input()
                    except EOFError:
                        pass
                else:
                    print("Non-interactive mode detected; waiting up to 5 minutes for manual login in the open browser...")
                    wait_for_auth_cookie(page, context, timeout_seconds=300)
                load_home_page(page)

        audio_ready = wait_for_audio_ready(page)
        if not audio_ready and username and password:
            print("Audio search module did not load; attempting login in case saved session is stale.")
            login_attempted = True
            try_auto_login(page, context, args.login_url, username, password)
            load_home_page(page)
            audio_ready = wait_for_audio_ready(page)

        if not audio_ready:
            print("Audio search module did not become ready.", file=sys.stderr)
            if not login_attempted and not (username and password):
                print("No login credentials were available for automatic login.", file=sys.stderr)
            browser.close()
            return 1

        audio_token, audio_module_id = detect_audio_module(page)
        if audio_token and not capture_config["token"]:
            capture_config["token"] = audio_token
        if capture_config["token"]:
            print(f"Targeting audio module token: {capture_config['token']}")

        if args.ui_only:
            # Fast path: no template capture needed when we only want on-page UI search.
            attempts = 0
            ok = False
            while attempts < 2:
                attempts += 1
                if attempts > 1:
                    reload_with_retry(page)
                    apply_content_width_override(page)
                    focus_outofthebox_widget(page)
                    ensure_dark_mode(page)
                wait_for_audio_ready(page)
                audio_token, audio_module_id = detect_audio_module(page)
                ok = submit_query_in_ui(
                    page,
                    args.query,
                    module_token=audio_token or capture_config["token"],
                    module_id=audio_module_id,
                )
                if not ok:
                    continue
                # Allow UI XHR/render to finish.
                if not safe_wait(page, 1300):
                    browser.close()
                    return 0
                if has_no_content_error(page):
                    print("Detected 'No content received' banner. Reloading and retrying once...")
                    continue
                break

            if not ok:
                print("Could not find the OutoftheBox audio search input in the UI.", file=sys.stderr)
                browser.close()
                return 1
            print("Query submitted in browser UI. Review the rendered results in the open window.")
            if args.stay_open_seconds <= 0:
                print("Close the browser window to end this script.")
                while True:
                    if not safe_wait(page, 500):
                        break
            else:
                if not safe_wait(page, args.stay_open_seconds * 1000):
                    browser.close()
                    return 0
            if args.storage_state and has_wp_login_cookie(context):
                state_path = Path(args.storage_state).expanduser().resolve()
                state_path.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(state_path))
                print(f"Saved storage state to {state_path}")
            elif args.storage_state:
                print("Skipping storage state save because browser context is not authenticated.")
            browser.close()
            return 0

        # Wait for a matching request that the page emits itself.
        deadline = time.time() + max(5, args.capture_timeout)
        while not captured and time.time() < deadline:
            try:
                page.wait_for_timeout(500)
            except PlaywrightTimeoutError:
                pass

        if not captured:
            print("No audio AJAX template captured automatically.")
            submitted = submit_query_in_ui(page, args.query, module_token=capture_config["token"], module_id=audio_module_id)
            if not submitted:
                print("Could not auto-submit audio field; submit in browser manually, then press Enter.")
                input()
            deadline = time.time() + 10
            while not captured and time.time() < deadline:
                if not safe_wait(page, 300):
                    break

        if not captured:
            print("Failed to capture OutoftheBox audio request template.", file=sys.stderr)
            browser.close()
            return 1

        template_form = dict(parse_qsl(captured["post_data"], keep_blank_values=True))
        template_form["query"] = args.query
        template_form["page_url"] = BASE_URL

        req_headers = json.loads(captured["headers_json"])
        ajax_headers = {
            "accept": req_headers.get("accept", "application/json, text/javascript, */*; q=0.01"),
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": "https://djpoolrecords.com",
            "referer": BASE_URL,
            "x-requested-with": req_headers.get("x-requested-with", "XMLHttpRequest"),
            "user-agent": req_headers.get("user-agent", "Mozilla/5.0"),
        }

        resp = context.request.post(captured["url"], form=template_form, headers=ajax_headers, timeout=30_000)
        raw = resp.body()
        output_path.write_bytes(raw)

        print(f"HTTP status: {resp.status}")
        print(f"Content-Type: {resp.headers.get('content-type', '')}")
        print(f"Response bytes: {len(raw)}")
        print(f"Saved response to {output_path}")

        if args.debug_file:
            debug_path = Path(args.debug_file).expanduser().resolve()
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug = {
                "captured_url": captured.get("url"),
                "captured_method": captured.get("method"),
                "captured_post_data": captured.get("post_data"),
                "submitted_form": template_form,
                "status": resp.status,
                "content_type": resp.headers.get("content-type", ""),
                "response_bytes": len(raw),
                "final_page_url": page.url,
                "has_wp_login_cookie": has_wp_login_cookie(context),
            }
            debug_path.write_text(json.dumps(debug, indent=2), encoding="utf-8")
            print(f"Saved debug metadata to {debug_path}")

        if args.storage_state and has_wp_login_cookie(context):
            state_path = Path(args.storage_state).expanduser().resolve()
            state_path.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(state_path))
            print(f"Saved storage state to {state_path}")
        elif args.storage_state:
            print("Skipping storage state save because browser context is not authenticated.")

        if args.pretty_print:
            pretty_print_files(raw, limit=args.pretty_limit)

        browser.close()

    try:
        shutil.rmtree(staging_downloads_dir, ignore_errors=True)
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
