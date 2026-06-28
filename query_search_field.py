#!/usr/bin/env python3
"""Query DJPoolRecords admin-ajax search endpoint and write response to a file."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode
from urllib.request import Request, urlopen

URL = "https://djpoolrecords.com/wp-admin/admin-ajax.php"
DEFAULT_REFERER = "https://djpoolrecords.com/"


def env_or_arg(value: str | None, env_name: str) -> str | None:
    return value if value is not None else os.getenv(env_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send the outofthebox-get-filelist query and write the response to a file."
    )
    parser.add_argument("--query", default="example query", help="Search query string")
    parser.add_argument("--output", default="response.json", help="Output file path")
    parser.add_argument("--cookie", help="Cookie header value")
    parser.add_argument("--nonce", help="_ajax_nonce value")
    parser.add_argument("--listtoken", help="listtoken value")
    parser.add_argument("--account-id", dest="account_id", help="account_id value")
    parser.add_argument("--lastpath", default="%2F", help="lastpath value (encoded path)")
    parser.add_argument("--sort", default="name:asc", help="sort value")
    parser.add_argument("--mobile", default="false", help="mobile value")
    parser.add_argument("--page-url", default=DEFAULT_REFERER, help="page_url value")
    parser.add_argument(
        "--raw-form",
        help="Send this exact application/x-www-form-urlencoded body without re-encoding",
    )
    parser.add_argument(
        "--debug-file",
        help="Write request/response metadata JSON (status, headers, body length) to this path",
    )
    parser.add_argument(
        "--referer",
        default=DEFAULT_REFERER,
        help="Referer header value",
    )
    parser.add_argument(
        "--pretty-print",
        action="store_true",
        help="Parse response JSON and print a readable file list",
    )
    parser.add_argument(
        "--pretty-limit",
        type=int,
        default=0,
        help="Limit pretty-printed rows (0 = no limit)",
    )
    parser.add_argument(
        "--probe-pagination",
        action="store_true",
        help="Try common pagination params and print discovered counts",
    )
    parser.add_argument(
        "--probe-max-pages",
        type=int,
        default=5,
        help="Max pages to try per pagination strategy in probe mode",
    )
    parser.add_argument(
        "--probe-step",
        type=int,
        default=40,
        help="Offset step used for offset-based probe strategies",
    )
    parser.add_argument(
        "--probe-advanced",
        action="store_true",
        help="Try additional action/folder/query parameter variants",
    )
    parser.add_argument(
        "--probe-advanced-max-cases",
        type=int,
        default=20,
        help="Maximum advanced probe variants to test",
    )
    parser.add_argument("--print-status", action="store_true", help="Print HTTP status and content type")
    return parser.parse_args()


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: max(0, width - 3)] + "..."


def pretty_print_files(raw: bytes, limit: int = 0) -> None:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        print(f"Pretty print skipped: response is not valid JSON ({exc})", file=sys.stderr)
        return

    html = payload.get("html")
    if not isinstance(html, str):
        print("Pretty print skipped: JSON has no 'html' field.", file=sys.stderr)
        return

    try:
        from bs4 import BeautifulSoup
    except Exception:
        print("Pretty print skipped: BeautifulSoup (bs4) not installed.", file=sys.stderr)
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
        title = name_node.get_text(" ", strip=True) if name_node else (entry.get("data-name") or "")
        size = size_node.get_text(" ", strip=True) if size_node else ""
        ext = title.rsplit(".", 1)[-1].lower() if "." in title else ""

        preview_link = ""
        preview_node = entry.select_one("a.entry_action_external_view")
        if preview_node:
            preview_link = preview_node.get("href") or ""

        download_link = ""
        dl_node = entry.select_one("a.entry_action_download")
        if dl_node:
            download_link = dl_node.get("href") or ""

        rows.append(
            {
                "name": title,
                "ext": ext,
                "size": size,
                "preview": preview_link,
                "download": download_link,
            }
        )

    if limit > 0:
        rows = rows[:limit]

    name_w = min(80, max(20, max(len(r["name"]) for r in rows)))
    ext_w = 6
    size_w = 10
    header = f"{'#':>3}  {'NAME':<{name_w}}  {'EXT':<{ext_w}}  {'SIZE':<{size_w}}  DOWNLOAD URL"
    print(header)
    print("-" * len(header))
    for idx, row in enumerate(rows, 1):
        name = _truncate(row["name"], name_w)
        line = f"{idx:>3}  {name:<{name_w}}  {row['ext']:<{ext_w}}  {row['size']:<{size_w}}  {row['download']}"
        print(line)
        if row["preview"]:
            print(f"     preview: {row['preview']}")

    total = payload.get("filescount")
    print(f"\nPrinted {len(rows)} file(s). filescount={total}")


def send_request(body_text: str, headers: dict[str, str]) -> tuple[bytes, int, str, dict[str, str]]:
    body = body_text.encode("utf-8")
    request = Request(URL, data=body, headers=headers, method="POST")

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            status_code = response.getcode()
            content_type = response.headers.get("Content-Type", "")
            response_headers = dict(response.headers.items())
    except HTTPError as exc:
        raw = exc.read()
        status_code = exc.code
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        response_headers = dict(exc.headers.items()) if exc.headers else {}

    return raw, status_code, content_type, response_headers


def extract_counts(raw: bytes) -> tuple[int | None, int | None]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None, None

    filescount = payload.get("filescount")
    html = payload.get("html", "")
    html_count = html.count("class='entry file") if isinstance(html, str) else None
    return filescount if isinstance(filescount, int) else None, html_count


def apply_updates_to_form(form_text: str, updates: dict[str, str]) -> str:
    items = parse_qsl(form_text, keep_blank_values=True)
    out: list[tuple[str, str]] = []
    updated_keys = set()
    for key, value in items:
        if key in updates:
            out.append((key, updates[key]))
            updated_keys.add(key)
        else:
            out.append((key, value))
    for key, value in updates.items():
        if key not in updated_keys:
            out.append((key, value))
    return urlencode(out, doseq=True)


def probe_pagination(
    base_form: str,
    headers: dict[str, str],
    base_filescount: int | None,
    base_html_count: int | None,
    max_pages: int,
    step: int,
) -> None:
    print("\nPagination probe:")
    print(
        f"- baseline filescount={base_filescount}, html_entries={base_html_count}, "
        f"max_pages={max_pages}, step={step}"
    )
    strategies = [
        ("page", lambda page: {"page": str(page)}),
        ("paged", lambda page: {"paged": str(page)}),
        ("page+per_page", lambda page: {"page": str(page), "per_page": "100"}),
        ("paged+per_page", lambda page: {"paged": str(page), "per_page": "100"}),
        ("offset", lambda page: {"offset": str((page - 1) * step)}),
        ("offset+limit", lambda page: {"offset": str((page - 1) * step), "limit": str(step)}),
        ("limit", lambda page: {"limit": str(page * step)}),
    ]

    any_change = False
    for label, update_fn in strategies:
        print(f"\nStrategy: {label}")
        for page in range(1, max_pages + 1):
            test_form = apply_updates_to_form(base_form, update_fn(page))
            try:
                raw, status_code, content_type, _ = send_request(test_form, headers)
            except URLError as exc:
                print(f"- p{page}: request failed ({exc})")
                continue

            fc, hc = extract_counts(raw)
            changed = (fc != base_filescount) or (hc != base_html_count)
            marker = "*" if changed else " "
            print(f"{marker} p{page}: status={status_code} filescount={fc} html_entries={hc} type={content_type}")
            if changed:
                any_change = True

    if not any_change:
        print("\nNo pagination variant changed the returned count in this probe range.")


def probe_advanced_variants(
    base_form: str,
    headers: dict[str, str],
    base_filescount: int | None,
    base_html_count: int | None,
    max_cases: int,
) -> None:
    print("\nAdvanced probe:")
    print(f"- baseline filescount={base_filescount}, html_entries={base_html_count}, max_cases={max_cases}")

    base_map = dict(parse_qsl(base_form, keep_blank_values=True))
    current_action = base_map.get("action", "")
    current_query = base_map.get("query", "")

    # Keep this constrained to avoid hammering the endpoint.
    variants: list[tuple[str, dict[str, str]]] = []

    action_candidates = [current_action, "letsbox-get-filelist", "outofthebox-get-filelist"]
    seen = set()
    for action in action_candidates:
        if action:
            key = ("action", action)
            if key not in seen:
                seen.add(key)
                variants.append((f"action={action}", {"action": action}))

    variants.extend(
        [
            ("drop lastFolder", {"lastFolder": ""}),
            ("drop folderPath", {"folderPath": ""}),
            ("folderPath=bnVsbA==", {"folderPath": "bnVsbA=="}),
            ("folderPath=%2F", {"folderPath": "/"}),
            ("folderPath=root", {"folderPath": "root"}),
            ("root lastFolder id", {"lastFolder": "82554928794"}),
            ("force mobile=true", {"mobile": "true"}),
        ]
    )

    if current_query:
        variants.extend(
            [
                ("query upper", {"query": current_query.upper()}),
                ("query wildcard right", {"query": f"{current_query}*"}),
                ("query wildcard both", {"query": f"*{current_query}*"}),
                ("query trailing space", {"query": f"{current_query} "}),
            ]
        )
    else:
        variants.extend(
            [
                ("query=drake", {"query": "drake"}),
                ("query=Drake", {"query": "Drake"}),
            ]
        )

    # Try common alternate search key names while keeping query too.
    if current_query:
        variants.extend(
            [
                ("add search", {"search": current_query}),
                ("add searchfor", {"searchfor": current_query}),
                ("add term", {"term": current_query}),
            ]
        )

    any_change = False
    tested = 0
    for label, updates in variants:
        if tested >= max_cases:
            break
        tested += 1
        test_form = apply_updates_to_form(base_form, updates)
        try:
            raw, status_code, content_type, _ = send_request(test_form, headers)
        except URLError as exc:
            print(f"- {label}: request failed ({exc})")
            continue

        fc, hc = extract_counts(raw)
        changed = (fc != base_filescount) or (hc != base_html_count)
        marker = "*" if changed else " "
        print(f"{marker} {label}: status={status_code} filescount={fc} html_entries={hc} type={content_type}")
        if changed:
            any_change = True

    if not any_change:
        print("\nNo advanced variant changed the returned count in this probe set.")


def main() -> int:
    args = parse_args()

    cookie = env_or_arg(args.cookie, "DJPOOL_COOKIE")
    nonce = env_or_arg(args.nonce, "DJPOOL_NONCE")
    listtoken = env_or_arg(args.listtoken, "DJPOOL_LISTTOKEN")
    account_id = env_or_arg(args.account_id, "DJPOOL_ACCOUNT_ID")

    missing = [
        name
        for name, value in {
            "cookie (--cookie or DJPOOL_COOKIE)": cookie,
            "nonce (--nonce or DJPOOL_NONCE)": nonce,
            "listtoken (--listtoken or DJPOOL_LISTTOKEN)": listtoken,
            "account_id (--account-id or DJPOOL_ACCOUNT_ID)": account_id,
        }.items()
        if not value
    ]
    if missing:
        print("Missing required values:", file=sys.stderr)
        for item in missing:
            print(f"- {item}", file=sys.stderr)
        return 2

    payload = None
    if args.raw_form:
        body_text = args.raw_form
    else:
        payload = {
            "listtoken": listtoken,
            "account_id": account_id,
            "lastpath": args.lastpath,
            "sort": args.sort,
            "action": "outofthebox-get-filelist",
            "_ajax_nonce": nonce,
            "mobile": args.mobile,
            "query": args.query,
            "page_url": args.page_url,
        }
        body_text = urlencode(payload)

    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": "https://djpoolrecords.com",
        "pragma": "no-cache",
        "referer": args.referer,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "x-requested-with": "XMLHttpRequest",
        "cookie": cookie,
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        ),
    }

    try:
        raw, status_code, content_type, response_headers = send_request(body_text, headers)
    except URLError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(raw)

    if args.debug_file:
        debug_path = Path(args.debug_file).expanduser().resolve()
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "url": URL,
            "status_code": status_code,
            "content_type": content_type,
            "response_bytes": len(raw),
            "response_headers": response_headers,
            "request_form_mode": "raw" if args.raw_form else "encoded",
            "request_form": body_text,
            "request_payload_map": payload,
        }
        debug_path.write_text(json.dumps(debug_payload, indent=2), encoding="utf-8")
        print(f"Saved debug metadata to {debug_path}")

    if args.print_status:
        print(f"HTTP status: {status_code}")
        print(f"Content-Type: {content_type}")
        print(f"Response bytes: {len(raw)}")

    # Optional hint for quick inspection when response is JSON.
    if "json" in content_type.lower():
        try:
            parsed = json.loads(raw.decode("utf-8"))
            keys = ", ".join(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__
            print(f"Saved JSON response ({keys}) to {output_path}")
        except Exception:
            print(f"Saved response to {output_path}")
    else:
        print(f"Saved response to {output_path}")

    if args.pretty_print:
        pretty_print_files(raw, limit=args.pretty_limit)

    if args.probe_pagination:
        base_filescount, base_html_count = extract_counts(raw)
        probe_pagination(
            base_form=body_text,
            headers=headers,
            base_filescount=base_filescount,
            base_html_count=base_html_count,
            max_pages=max(1, args.probe_max_pages),
            step=max(1, args.probe_step),
        )

    if args.probe_advanced:
        base_filescount, base_html_count = extract_counts(raw)
        probe_advanced_variants(
            base_form=body_text,
            headers=headers,
            base_filescount=base_filescount,
            base_html_count=base_html_count,
            max_cases=max(1, args.probe_advanced_max_cases),
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
