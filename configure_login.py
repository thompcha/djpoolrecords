#!/usr/bin/env python3
"""Store DJPoolRecords login credentials in macOS Keychain."""

from __future__ import annotations

import getpass
import subprocess
import sys

KEYCHAIN_SERVICE = "djpoolrecords"


def store_secret(account: str, value: str) -> None:
    subprocess.run(
        [
            "/usr/bin/security",
            "add-generic-password",
            "-U",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            account,
            "-w",
            value,
        ],
        check=True,
    )


def main() -> int:
    if sys.platform != "darwin":
        print("This setup utility requires macOS Keychain.", file=sys.stderr)
        return 2

    username = input("DJPoolRecords username/email: ").strip()
    password = getpass.getpass("DJPoolRecords password: ")
    if not username or not password:
        print("Username and password are required.", file=sys.stderr)
        return 2

    try:
        store_secret("username", username)
        store_secret("password", password)
    except subprocess.CalledProcessError as exc:
        print(f"Could not update macOS Keychain (exit {exc.returncode}).", file=sys.stderr)
        return 1

    print("DJPoolRecords credentials saved in macOS Keychain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
