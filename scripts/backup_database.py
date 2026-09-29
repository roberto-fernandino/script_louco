#!/usr/bin/env python3
"""Create a PostgreSQL SQL dump and deliver it to one Telegram chat."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy.engine import make_url


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def create_dump(database_url: str, output: Path) -> None:
    if shutil.which("pg_dump") is None:
        raise SystemExit("pg_dump was not found. Install the PostgreSQL client tools first.")

    url = make_url(database_url)
    if url.drivername.startswith("postgresql") is False:
        raise SystemExit("DATABASE_URL must be a PostgreSQL URL")

    command = ["pg_dump", "--no-owner", "--no-privileges", "--format=plain", "--file", str(output)]
    if url.host:
        command += ["--host", url.host]
    if url.port:
        command += ["--port", str(url.port)]
    if url.username:
        command += ["--username", url.username]
    if url.database:
        command += ["--dbname", url.database]

    environment = os.environ.copy()
    if url.password is not None:
        environment["PGPASSWORD"] = url.password

    try:
        subprocess.run(command, check=True, env=environment, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or "pg_dump failed").strip()
        raise SystemExit(f"Database backup failed: {details}") from error


def send_to_telegram(token: str, chat_id: str, dump: Path) -> None:
    endpoint = f"https://api.telegram.org/bot{token}/sendDocument"
    caption = f"Database backup {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    with dump.open("rb") as handle:
        response = httpx.post(
            endpoint,
            data={"chat_id": chat_id, "caption": caption},
            files={"document": (dump.name, handle, "application/sql")},
            timeout=120.0,
        )
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise SystemExit(f"Telegram rejected the backup: {result.get('description', 'unknown error')}")


def run_backup(database_url: str, token: str, chat_id: str) -> None:
    with tempfile.TemporaryDirectory(prefix="script-louco-backup-") as directory:
        dump = Path(directory) / f"database-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sql"
        create_dump(database_url, dump)
        send_to_telegram(token, chat_id, dump)
        print(f"Backup sent to Telegram chat {chat_id}: {dump.name}")


def main() -> int:
    run_backup(
        required("DATABASE_URL"),
        required("TELEGRAM_BOT_TOKEN"),
        required("TELEGRAM_CHAT_ID"),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as error:
        raise SystemExit(f"Telegram request failed: {error}") from error
