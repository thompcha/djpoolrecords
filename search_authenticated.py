#!/usr/bin/env python3
"""Login to DJPoolRecords, submit homepage file search query, save response."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from http.cookies import SimpleCookie

try:
    import requests
except Exception as exc:  # pragma: no cover
    print(f"Missing dependency: requests ({exc})", file=sys.stderr)
    raise SystemExit(2)


DEFAULT_BASE_URL = "https://djpoolrecords.com"
WP_LOGIN_PATH = "/wp-login.php"
AJAX_PATH = "/wp-admin/admin-ajax.php"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Authenticate to WordPress homepage and query DJPoolRecords AJAX search."
    )
    parser.add_argument("--query", required=True, help="Search query text")
    parser.add_argument("--username", help="WordPress username/email (or DJPOOL_USER env)")
    parser.add_argument("--password", help="WordPress password (or DJPOOL_PASS env)")
    parser.add_argument(
        "--cookie",
        default="",
        help="Raw Cookie header string from an authenticated browser session (skips login)",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Site base URL")
    parser.add_argument("--output", default="response.json", help="Output response file")
    parser.add_argument("--debug-file", default="", help="Write debug metadata JSON file")
    parser.add_argument("--pretty-print", action="store_true", help="Pretty print file results")
    parser.add_argument("--pretty-limit", type=int, default=20, help="Pretty print row limit (0 = all)")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds")

    # Optional overrides if extraction fails.
    parser.add_argument("--action", default="", help="Override AJAX action")
    parser.add_argument("--listtoken", default="", help="Override listtoken")
    parser.add_argument("--account-id", default="", help="Override account_id")
    parser.add_argument("--nonce", default="", help="Override _ajax_nonce")
    parser.add_argument("--last-folder", default="", help="Override lastFolder")
    parser.add_argument("--folder-path", default="", help="Override folderPath")
    parser.add_argument("--sort", default="", help="Override sort")
    parser.add_argument("--mobile", default="", help="Override mobile")
    return parser.parse_args()


def get_secret(value: str, env_name: str) -> str:
    v = value or os.getenv(env_name, "")
    if not v:
        print(f"Missing {env_name} (or corresponding CLI arg).", file=sys.stderr)
        raise SystemExit(2)
    return v


def apply_cookie_header_to_session(session: requests.Session, cookie_header: str) -> None:
    c = SimpleCookie()
    c.load(cookie_header)
    for key, morsel in c.items():
        session.cookies.set(key, morsel.value)


def find_first(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1)
    return ""


def extract_ajax_values(html: str) -> dict[str, str]:
    values = {
        "action": find_first(
            [
                r"[?&]action=(letsbox-get-filelist|outofthebox-get-filelist)\b",
                r"['\"]action['\"]\s*[:=]\s*['\"](letsbox-get-filelist|outofthebox-get-filelist)['\"]",
            ],
            html,
        )
        or "letsbox-get-filelist",
        "listtoken": find_first(
            [r"['\"]listtoken['\"]\s*[:=]\s*['\"]([a-zA-Z0-9]+)['\"]", r"[?&]listtoken=([a-zA-Z0-9]+)"],
            html,
        ),
        "account_id": find_first(
            [r"['\"]account_id['\"]\s*[:=]\s*['\"]([^'\"]+)['\"]", r"[?&]account_id=([^&\"']+)"],
            html,
        ),
        "_ajax_nonce": find_first(
            [r"['\"]_ajax_nonce['\"]\s*[:=]\s*['\"]([a-zA-Z0-9]+)['\"]", r"[?&]_ajax_nonce=([a-zA-Z0-9]+)"],
            html,
        ),
        "lastFolder": find_first([r"['\"]lastFolder['\"]\s*[:=]\s*['\"]([^'\"]*)['\"]"], html),
        "folderPath": find_first([r"['\"]folderPath['\"]\s*[:=]\s*['\"]([^'\"]*)['\"]"], html),
        "sort": find_first([r"['\"]sort['\"]\s*[:=]\s*['\"]([^'\"]+)['\"]"], html) or "name:asc",
        "mobile": find_first([r"['\"]mobile['\"]\s*[:=]\s*(true|false|['\"][^'\"]+['\"])"], html),
    }

    if values["mobile"]:
        values["mobile"] = values["mobile"].strip("'\"")
    else:
        values["mobile"] = "false"

    return values


def pretty_print_files(raw: bytes, limit: int) -> None:
    try:
        from bs4 import BeautifulSoup
    except Exception:
        print("Pretty print skipped: BeautifulSoup (bs4) not installed.", file=sys.stderr)
        return

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        print(f"Pretty print skipped: invalid JSON ({exc})", file=sys.stderr)
        return

    html = payload.get("html")
    if not isinstance(html, str):
        print("Pretty print skipped: no html field in response.", file=sys.stderr)
        return

    soup = BeautifulSoup(html, "html.parser")
    entries = soup.select(".entry.file")
    if not entries:
        print("No file entries found.")
        return

    rows: list[tuple[str, str, str]] = []
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


def main() -> int:
    args = parse_args()
    use_cookie_login = bool(args.cookie.strip())
    username = ""
    password = ""
    if not use_cookie_login:
        username = get_secret(args.username or "", "DJPOOL_USER")
        password = get_secret(args.password or "", "DJPOOL_PASS")

    base_url = args.base_url.rstrip("/")
    login_url = f"{base_url}{WP_LOGIN_PATH}"
    ajax_url = f"{base_url}{AJAX_PATH}"
    homepage_url = f"{base_url}/"

    session = requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        )
    }

    if use_cookie_login:
        apply_cookie_header_to_session(session, args.cookie.strip())
        print("Using provided browser cookie header; skipping wp-login flow.")
    else:
        # Prime cookies for WordPress login.
        session.get(login_url, headers=headers, timeout=args.timeout)

        login_form = {
            "log": username,
            "pwd": password,
            "rememberme": "forever",
            "wp-submit": "Log In",
            "redirect_to": homepage_url,
            "testcookie": "1",
        }
        login_resp = session.post(login_url, headers=headers, data=login_form, timeout=args.timeout, allow_redirects=True)
        login_text_lower = login_resp.text.lower()
        if "login_error" in login_text_lower:
            msg = find_first([r"<div[^>]*id=['\"]login_error['\"][^>]*>(.*?)</div>"], login_resp.text)
            if msg:
                msg = re.sub(r"<[^>]+>", " ", msg)
                msg = re.sub(r"\s+", " ", msg).strip()
            print("Login failed: login_error detected.", file=sys.stderr)
            if msg:
                print(f"Site message: {msg}", file=sys.stderr)
            print(f"Final login URL: {login_resp.url}", file=sys.stderr)
            return 1
        if not any(k.startswith("wordpress_logged_in_") for k in session.cookies.keys()):
            print("Login may have failed: wordpress_logged_in cookie not found.", file=sys.stderr)
            print(f"Final login URL: {login_resp.url}", file=sys.stderr)
            if "cloudflare" in login_text_lower or "attention required" in login_text_lower:
                print("Possible Cloudflare/WAF challenge detected in login response.", file=sys.stderr)
            elif "wp-login.php" in login_resp.url:
                print("Still on wp-login.php after submit; credentials or required challenge may be invalid.", file=sys.stderr)
            cookie_keys = ", ".join(sorted(session.cookies.keys()))
            if cookie_keys:
                print(f"Cookies set (non-auth): {cookie_keys}", file=sys.stderr)
            return 1

    home_resp = session.get(homepage_url, headers=headers, timeout=args.timeout)
    home_html = home_resp.text
    extracted = extract_ajax_values(home_html)

    form = {
        "listtoken": args.listtoken or extracted["listtoken"],
        "account_id": args.account_id or extracted["account_id"],
        "lastFolder": args.last_folder or extracted["lastFolder"],
        "folderPath": args.folder_path or extracted["folderPath"] or "bnVsbA==",
        "sort": args.sort or extracted["sort"] or "name:asc",
        "action": args.action or extracted["action"] or "letsbox-get-filelist",
        "_ajax_nonce": args.nonce or extracted["_ajax_nonce"],
        "mobile": args.mobile or extracted["mobile"] or "false",
        "query": args.query,
        "page_url": homepage_url,
    }

    required = ["listtoken", "account_id", "_ajax_nonce", "action"]
    missing = [k for k in required if not form.get(k)]
    if missing:
        print("Missing required AJAX values after extraction:", file=sys.stderr)
        for key in missing:
            print(f"- {key}", file=sys.stderr)
        print("Use override flags (--listtoken/--account-id/--nonce/--action).", file=sys.stderr)
        return 2

    ajax_headers = {
        **headers,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": base_url,
        "Referer": homepage_url,
        "X-Requested-With": "XMLHttpRequest",
    }
    ajax_resp = session.post(ajax_url, headers=ajax_headers, data=form, timeout=args.timeout)
    raw = ajax_resp.content

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(raw)

    print(f"HTTP status: {ajax_resp.status_code}")
    print(f"Content-Type: {ajax_resp.headers.get('Content-Type', '')}")
    print(f"Response bytes: {len(raw)}")
    print(f"Saved response to {output_path}")

    if args.debug_file:
        debug_payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "login_url": login_url,
            "homepage_url": homepage_url,
            "ajax_url": ajax_url,
            "status_code": ajax_resp.status_code,
            "content_type": ajax_resp.headers.get("Content-Type", ""),
            "response_bytes": len(raw),
            "extracted_values": extracted,
            "submitted_form": form,
        }
        debug_path = Path(args.debug_file).expanduser().resolve()
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(json.dumps(debug_payload, indent=2), encoding="utf-8")
        print(f"Saved debug metadata to {debug_path}")

    if args.pretty_print:
        pretty_print_files(raw, limit=args.pretty_limit)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
