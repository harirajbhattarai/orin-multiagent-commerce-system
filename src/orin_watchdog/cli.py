"""One-shot, read-only watchdog command."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from orin_control.repository import create_database_engine
from orin_control.secrets import read_private_secret
from orin_watchdog.repository import WatchdogRepository
from orin_watchdog.service import CLIENT_ID, evaluate, source_job_key


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="orin-watchdog",
        description="Check the fixed Hoverboard Store scheduler receipt without mutations.",
    )


def database_url_from_environment() -> str:
    direct = os.environ.get("ORIN_WATCHDOG_DATABASE_URL")
    secret_file = os.environ.get("ORIN_WATCHDOG_DATABASE_URL_FILE")
    if bool(direct) == bool(secret_file):
        raise ValueError(
            "configure exactly one of ORIN_WATCHDOG_DATABASE_URL "
            "or ORIN_WATCHDOG_DATABASE_URL_FILE"
        )
    if direct:
        return direct
    assert secret_file is not None
    return read_private_secret(Path(secret_file), label="watchdog database URL")


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    repository: WatchdogRepository | None = None
    try:
        database_url = database_url_from_environment()
        repository = WatchdogRepository(
            create_database_engine(database_url, pool_size=1),
            expected_role=os.environ.get(
                "ORIN_WATCHDOG_DATABASE_ROLE",
                "orin_watchdog",
            ),
        )
        now = datetime.now(UTC)
        snapshot = repository.snapshot(
            client_id=CLIENT_ID,
            source_job_key=source_job_key(now),
        )
        result = evaluate(snapshot, now=now)
        print(json.dumps(result.to_dict(), sort_keys=True))
        return 1 if result.status == "alert" else 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "code": "ORIN_WATCHDOG_FAILED",
                    "detail": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        return 2
    finally:
        if repository is not None:
            repository.close()


if __name__ == "__main__":
    raise SystemExit(main())
