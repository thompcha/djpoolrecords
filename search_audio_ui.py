#!/usr/bin/env python3
"""One-argument wrapper for DJPoolRecords audio UI search."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PLAYWRIGHT_SCRIPT = BASE_DIR / "browser_search_playwright.py"
DEFAULT_STATE = BASE_DIR / "djpool_state.json"
DEFAULT_AUDIO_TOKEN = "c91b8b53c4c2dfa5695a9f4ee991f2f4"
DEFAULT_LOGIN_URL = "https://djpoolrecords.com/djpoolrecords-user-login/"
CONTRACTION_STOPWORDS = (
    "i(?:['\u2019]?d|['\u2019]?ll|['\u2019]?m|['\u2019]?ve)",
    "you(?:['\u2019]?d|['\u2019]?ll|['\u2019]?re|['\u2019]?ve)",
    "we(?:['\u2019]?d|['\u2019]?ll|['\u2019]?re|['\u2019]?ve)",
    "they(?:['\u2019]?d|['\u2019]?ll|['\u2019]?re|['\u2019]?ve)",
    "he(?:['\u2019]?d|['\u2019]?ll|['\u2019]?s)",
    "she(?:['\u2019]?d|['\u2019]?ll|['\u2019]?s)",
    "it(?:['\u2019]?d|['\u2019]?ll|['\u2019]?s)",
    "that(?:['\u2019]?d|['\u2019]?ll|['\u2019]?s)",
    "there(?:['\u2019]?d|['\u2019]?ll|['\u2019]?s)",
    "what(?:['\u2019]?d|['\u2019]?ll|['\u2019]?s)",
    "who(?:['\u2019]?d|['\u2019]?ll|['\u2019]?s)",
    "ain['\u2019]?t",
    "aren['\u2019]?t",
    "can['\u2019]?t",
    "couldn['\u2019]?t",
    "didn['\u2019]?t",
    "doesn['\u2019]?t",
    "don['\u2019]?t",
    "hadn['\u2019]?t",
    "hasn['\u2019]?t",
    "haven['\u2019]?t",
    "isn['\u2019]?t",
    "mustn['\u2019]?t",
    "needn['\u2019]?t",
    "shouldn['\u2019]?t",
    "wasn['\u2019]?t",
    "weren['\u2019]?t",
    "won['\u2019]?t",
    "wouldn['\u2019]?t",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run DJPoolRecords audio search UI from a query or filename."
    )
    parser.add_argument(
        "input_value",
        help="Either a raw query or a file path; if path exists, filename transforms are applied.",
    )
    parser.add_argument(
        "--literal-query",
        action="store_true",
        help="Treat input_value as query text even if it looks like a file path.",
    )
    parser.add_argument(
        "--print-query",
        action="store_true",
        help="Print the final transformed query before launching browser search.",
    )
    return parser.parse_args()


def remove_explicit(name: str) -> str:
    match = re.search(r" \(explicit\)", name, flags=re.IGNORECASE)
    if not match:
        return name
    return name[: match.start()]


def remove_diacritics(text: str) -> str:
    # Superset of the AppleScript vowel replacements.
    normalized = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def truncate_after_keywords(text: str) -> str:
    if not text:
        return text

    truncate_pos = len(text)

    for ch in [",", "(", "[", "&"]:
        idx = text.find(ch)
        if idx != -1:
            truncate_pos = min(truncate_pos, idx)

    ft_match = re.search(r"\b(?:ft|feat)\b\.?", text, flags=re.IGNORECASE)
    if ft_match:
        truncate_pos = min(truncate_pos, ft_match.start())

    out = text[:truncate_pos].rstrip()
    return out


def remove_query_stopwords(text: str) -> str:
    # Strip common artist prefixes that reduce match quality in DJPoolRecords.
    text = re.sub(r"\b(?:dj|grupo)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(
        rf"\b(?:{'|'.join(CONTRACTION_STOPWORDS)})\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s{2,}", " ", text)


def filename_to_query(input_path: Path) -> str:
    name = input_path.name
    if "." in name:
        name = name.rsplit(".", 1)[0]

    name = remove_explicit(name)
    name = remove_diacritics(name)
    name = name.replace("_", " ")

    if " - " in name:
        artist, title = name.split(" - ", 1)
    else:
        artist, title = name, ""

    artist = truncate_after_keywords(artist)
    title = truncate_after_keywords(title)

    search = f"{artist} - {title}"
    search = remove_query_stopwords(search).strip()
    return search


def resolve_query(args: argparse.Namespace) -> str:
    raw = args.input_value.strip()
    # Handle pasted paths wrapped in matching quotes.
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        raw = raw[1:-1].strip()

    if args.literal_query:
        return remove_query_stopwords(raw).strip()

    maybe_path = Path(raw).expanduser()
    if maybe_path.exists():
        return filename_to_query(maybe_path)

    return remove_query_stopwords(raw).strip()


def main() -> int:
    args = parse_args()
    final_query = resolve_query(args)
    if args.print_query:
        print(final_query)
    if not final_query:
        print("Final query is empty after transformations.", file=sys.stderr)
        return 2

    cmd = [
        sys.executable,
        str(PLAYWRIGHT_SCRIPT),
        "--query",
        final_query,
        "--headed",
        "--ui-only",
        "--stay-open-seconds",
        "0",
        "--audio-token",
        DEFAULT_AUDIO_TOKEN,
        "--login-url",
        DEFAULT_LOGIN_URL,
        "--storage-state",
        str(DEFAULT_STATE),
    ]

    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
