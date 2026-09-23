import asyncio
import fcntl
import gzip
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import boto3
import postgresql_binaries
from botocore.config import Config

from .config import get_settings

logger = logging.getLogger("uvicorn.error")

# Written after a successful upload; delete it to allow another backup.
MARKER_PATH = Path(__file__).resolve().parents[1] / ".backup_done"
LOCK_PATH = Path(__file__).resolve().parents[1] / ".backup.lock"


def backup_database() -> str:
    settings = get_settings()
    if not all((settings.s3_bucket, settings.s3_access_key_id, settings.s3_secret_access_key)):
        raise RuntimeError("S3 backup configuration is incomplete")
    # pg_dump speaks libpq URLs, not SQLAlchemy driver URLs.
    database_url = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    database = database_url.rsplit("/", 1)[-1].split("?", 1)[0] or "database"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"{settings.s3_prefix}/{database}-{timestamp}.sql.gz"
    pg_dump = postgresql_binaries.bin() / "pg_dump"

    with tempfile.TemporaryDirectory() as tmp:
        dump_path = Path(tmp) / "dump.sql.gz"
        error_path = Path(tmp) / "pg_dump.err"
        with error_path.open("wb") as errors:
            proc = subprocess.Popen(
                [str(pg_dump), "--no-owner", "--no-privileges", database_url],
                stdout=subprocess.PIPE,
                stderr=errors,
            )
            assert proc.stdout is not None
            with gzip.open(dump_path, "wb") as out:
                shutil.copyfileobj(proc.stdout, out)
            returncode = proc.wait()
        if returncode != 0:
            stderr = error_path.read_text(errors="replace").strip()
            raise RuntimeError(f"pg_dump exited with {returncode}: {stderr}")

        s3 = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            # GCS rejects the default boto3 flexible checksums.
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        s3.upload_file(str(dump_path), settings.s3_bucket, key)

    return f"s3://{settings.s3_bucket}/{key}"


def backup_once() -> str | None:
    # The lock keeps reloads and multiple workers from racing; the marker makes it once ever.
    with LOCK_PATH.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        if MARKER_PATH.exists():
            return None
        location = backup_database()
        MARKER_PATH.write_text(f"{datetime.now(timezone.utc).isoformat()} {location}\n")
        return location


async def run_startup_backup() -> None:
    # Runs off the event loop and never raises, so a failed backup cannot take the API down.
    if MARKER_PATH.exists():
        return
    try:
        logger.info("Database backup started")
        location = await asyncio.to_thread(backup_once)
        if location:
            logger.info("Database backup uploaded to %s", location)
        else:
            logger.info("Database backup skipped: already done or running elsewhere")
    except Exception:
        logger.exception("Database backup failed")
