"""Database-aware health check for the scheduler-trigger sidecar."""

from __future__ import annotations

import stat
import sys

from orin_control.repository import create_database_engine
from orin_scheduler_trigger.repository import SchedulerRepository
from orin_scheduler_trigger.server import Settings


def main() -> int:
    repository: SchedulerRepository | None = None
    try:
        settings = Settings()  # type: ignore[call-arg]
        engine = create_database_engine(settings.resolved_database_url(), pool_size=1)
        repository = SchedulerRepository(engine, expected_role=settings.database_role)
        repository.ping()
        socket_mode = settings.socket_path.stat().st_mode
        if not stat.S_ISSOCK(socket_mode):
            raise RuntimeError("scheduler trigger socket is unavailable")
    except Exception:
        print("ORIN_SCHEDULER_TRIGGER_UNHEALTHY", file=sys.stderr)
        return 1
    finally:
        if repository is not None:
            repository.close()
    print("ORIN_SCHEDULER_TRIGGER_HEALTHY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
