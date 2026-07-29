"""Redacted database and role readiness check for the watchdog container."""

from __future__ import annotations

import sys

from orin_control.repository import create_database_engine
from orin_watchdog.repository import WatchdogRepository
from orin_watchdog.server import Settings


def main() -> int:
    repository: WatchdogRepository | None = None
    try:
        settings = Settings()  # type: ignore[call-arg]
        repository = WatchdogRepository(
            create_database_engine(settings.resolved_database_url(), pool_size=1),
            expected_role=settings.database_role,
        )
        repository.ping()
        if not settings.socket_path.is_socket():
            raise RuntimeError("watchdog socket is unavailable")
        return 0
    except Exception as exc:
        print(f"watchdog healthcheck failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        if repository is not None:
            repository.close()


if __name__ == "__main__":
    raise SystemExit(main())
