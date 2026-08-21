"""Idempotently install the paused Prefect shadow deployment."""

from __future__ import annotations

import asyncio
import os
import subprocess

from prefect.client.orchestration import get_client
from prefect.client.schemas.objects import (
    ConcurrencyLimitConfig,
    ConcurrencyLimitStrategy,
)
from prefect.schedules import Cron
from prefect.types.entrypoint import EntrypointType

from orin_prefect_owner.flow import (
    hbstore_daily_scheduler_flow,
    hbstore_owner_commissioning_flow,
    hcs_daily_scheduler_flow,
)

from .flow import hbstore_shadow_flow


WORK_POOL_NAME = "orin-shadow-process"
DEPLOYMENT_NAME = "orin-hbstore-shadow"
OWNER_WORK_POOL_NAME = "orin-owner-process"
OWNER_DEPLOYMENT_NAME = "orin-hbstore-owner-commissioning"
SCHEDULER_DEPLOYMENT_NAME = "orin-hbstore-prefect-scheduler"
SCHEDULER_CRON = "0 11 * * *"
SCHEDULER_TIMEZONE = "Europe/London"
SCHEDULER_SLUG = "hbstore-daily-dry-run"
HCS_OWNER_WORK_POOL_NAME = "orin-hcs-owner-process"
HCS_SCHEDULER_DEPLOYMENT_NAME = "orin-hcs-prefect-scheduler"
HCS_SCHEDULER_CRON = "30 11 * * *"
HCS_SCHEDULER_TIMEZONE = "Europe/London"
HCS_SCHEDULER_SLUG = "hcs-daily-dry-run"


async def _verify() -> None:
    async with get_client() as client:
        pool = await client.read_work_pool(WORK_POOL_NAME)
        if not pool.is_paused or pool.concurrency_limit != 1:
            raise RuntimeError("shadow work pool must be paused with concurrency one")
        deployment = await client.read_deployment_by_name(
            f"orin-hbstore-shadow/{DEPLOYMENT_NAME}"
        )
        if deployment.paused is not True:
            raise RuntimeError("shadow deployment must remain paused")
        if deployment.schedules:
            raise RuntimeError("shadow deployment must not have a schedule")
        owner_pool = await client.read_work_pool(OWNER_WORK_POOL_NAME)
        if not owner_pool.is_paused or owner_pool.concurrency_limit != 1:
            raise RuntimeError("owner work pool must be paused with concurrency one")
        owner_deployment = await client.read_deployment_by_name(
            f"orin-hbstore-owner-commissioning/{OWNER_DEPLOYMENT_NAME}"
        )
        if owner_deployment.paused is not True:
            raise RuntimeError("owner deployment must remain paused")
        if owner_deployment.schedules:
            raise RuntimeError("owner deployment must not have a schedule")
        scheduler_deployment = await client.read_deployment_by_name(
            f"orin-hbstore-prefect-scheduler/{SCHEDULER_DEPLOYMENT_NAME}"
        )
        if scheduler_deployment.paused is not True:
            raise RuntimeError("Prefect scheduler deployment must remain paused")
        if len(scheduler_deployment.schedules) != 1:
            raise RuntimeError("Prefect scheduler must have exactly one schedule")
        scheduler = scheduler_deployment.schedules[0]
        if scheduler.active:
            raise RuntimeError("Prefect scheduler schedule must remain inactive")
        if scheduler.slug != SCHEDULER_SLUG:
            raise RuntimeError("Prefect scheduler schedule slug is invalid")
        if scheduler.schedule.cron != SCHEDULER_CRON:
            raise RuntimeError("Prefect scheduler cron is invalid")
        if scheduler.schedule.timezone != SCHEDULER_TIMEZONE:
            raise RuntimeError("Prefect scheduler timezone is invalid")
        hcs_pool = await client.read_work_pool(HCS_OWNER_WORK_POOL_NAME)
        if not hcs_pool.is_paused or hcs_pool.concurrency_limit != 1:
            raise RuntimeError("HCS owner work pool must be paused with concurrency one")
        hcs_deployment = await client.read_deployment_by_name(
            f"orin-hcs-prefect-scheduler/{HCS_SCHEDULER_DEPLOYMENT_NAME}"
        )
        if hcs_deployment.paused is not True:
            raise RuntimeError("HCS scheduler deployment must remain paused")
        if len(hcs_deployment.schedules) != 1:
            raise RuntimeError("HCS scheduler must have exactly one schedule")
        hcs_schedule = hcs_deployment.schedules[0]
        if hcs_schedule.active:
            raise RuntimeError("HCS scheduler schedule must remain inactive")
        if hcs_schedule.slug != HCS_SCHEDULER_SLUG:
            raise RuntimeError("HCS scheduler schedule slug is invalid")
        if hcs_schedule.schedule.cron != HCS_SCHEDULER_CRON:
            raise RuntimeError("HCS scheduler cron is invalid")
        if hcs_schedule.schedule.timezone != HCS_SCHEDULER_TIMEZONE:
            raise RuntimeError("HCS scheduler timezone is invalid")


def main() -> None:
    subprocess.run(
        [
            "prefect",
            "work-pool",
            "create",
            "--type",
            "process",
            "--paused",
            "--overwrite",
            WORK_POOL_NAME,
        ],
        check=True,
    )
    subprocess.run(
        [
            "prefect",
            "work-pool",
            "create",
            "--type",
            "process",
            "--paused",
            "--overwrite",
            HCS_OWNER_WORK_POOL_NAME,
        ],
        check=True,
    )
    subprocess.run(
        [
            "prefect",
            "work-pool",
            "create",
            "--type",
            "process",
            "--paused",
            "--overwrite",
            OWNER_WORK_POOL_NAME,
        ],
        check=True,
    )
    subprocess.run(
        [
            "prefect",
            "work-pool",
            "set-concurrency-limit",
            HCS_OWNER_WORK_POOL_NAME,
            "1",
        ],
        check=True,
    )
    subprocess.run(
        [
            "prefect",
            "work-pool",
            "set-concurrency-limit",
            OWNER_WORK_POOL_NAME,
            "1",
        ],
        check=True,
    )
    subprocess.run(
        [
            "prefect",
            "work-pool",
            "set-concurrency-limit",
            WORK_POOL_NAME,
            "1",
        ],
        check=True,
    )
    deployment = hbstore_shadow_flow.to_deployment(
        name=DEPLOYMENT_NAME,
        paused=True,
        schedules=[],
        concurrency_limit=ConcurrencyLimitConfig(
            limit=1,
            collision_strategy=ConcurrencyLimitStrategy.CANCEL_NEW,
        ),
        parameters={"as_of_date": None},
        tags=["orin", "shadow", "hoverboard_store", "no-shopify-writes"],
        version=os.environ.get("ORIN_CODE_VERSION", "dev"),
        work_pool_name=WORK_POOL_NAME,
        entrypoint_type=EntrypointType.MODULE_PATH,
        job_variables={"working_dir": "/app"},
    )
    deployment.apply()
    owner_deployment = hbstore_owner_commissioning_flow.to_deployment(
        name=OWNER_DEPLOYMENT_NAME,
        paused=True,
        schedules=[],
        concurrency_limit=ConcurrencyLimitConfig(
            limit=1,
            collision_strategy=ConcurrencyLimitStrategy.CANCEL_NEW,
        ),
        tags=[
            "orin",
            "commissioning",
            "hoverboard_store",
            "dry-run-only",
            "no-shopify-credentials",
        ],
        version=os.environ.get("ORIN_CODE_VERSION", "dev"),
        work_pool_name=OWNER_WORK_POOL_NAME,
        entrypoint_type=EntrypointType.MODULE_PATH,
        job_variables={"working_dir": "/app"},
    )
    owner_deployment.apply()
    scheduler_deployment = hbstore_daily_scheduler_flow.to_deployment(
        name=SCHEDULER_DEPLOYMENT_NAME,
        paused=True,
        schedules=[
            Cron(
                SCHEDULER_CRON,
                timezone=SCHEDULER_TIMEZONE,
                active=False,
                slug=SCHEDULER_SLUG,
            )
        ],
        concurrency_limit=ConcurrencyLimitConfig(
            limit=1,
            collision_strategy=ConcurrencyLimitStrategy.CANCEL_NEW,
        ),
        tags=[
            "orin",
            "scheduler",
            "hoverboard_store",
            "dry-run-only",
            "no-shopify-credentials",
            "disabled-by-default",
        ],
        version=os.environ.get("ORIN_CODE_VERSION", "dev"),
        work_pool_name=OWNER_WORK_POOL_NAME,
        entrypoint_type=EntrypointType.MODULE_PATH,
        job_variables={"working_dir": "/app"},
    )
    scheduler_deployment.apply()
    hcs_scheduler_deployment = hcs_daily_scheduler_flow.to_deployment(
        name=HCS_SCHEDULER_DEPLOYMENT_NAME,
        paused=True,
        schedules=[
            Cron(
                HCS_SCHEDULER_CRON,
                timezone=HCS_SCHEDULER_TIMEZONE,
                active=False,
                slug=HCS_SCHEDULER_SLUG,
            )
        ],
        concurrency_limit=ConcurrencyLimitConfig(
            limit=1,
            collision_strategy=ConcurrencyLimitStrategy.CANCEL_NEW,
        ),
        tags=[
            "orin",
            "scheduler",
            "hcs_gadgets",
            "dry-run-only",
            "no-shopify-credentials",
            "disabled-by-default",
        ],
        version=os.environ.get("ORIN_CODE_VERSION", "dev"),
        work_pool_name=HCS_OWNER_WORK_POOL_NAME,
        entrypoint_type=EntrypointType.MODULE_PATH,
        job_variables={"working_dir": "/app"},
    )
    hcs_scheduler_deployment.apply()
    subprocess.run(["prefect", "work-pool", "pause", WORK_POOL_NAME], check=True)
    subprocess.run(
        ["prefect", "work-pool", "pause", OWNER_WORK_POOL_NAME], check=True
    )
    subprocess.run(
        ["prefect", "work-pool", "pause", HCS_OWNER_WORK_POOL_NAME], check=True
    )
    asyncio.run(_verify())
    print("ORIN_PREFECT_SHADOW_BOOTSTRAP_OK")


if __name__ == "__main__":
    main()
