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
from prefect.types.entrypoint import EntrypointType

from orin_prefect_owner.flow import hbstore_owner_commissioning_flow

from .flow import hbstore_shadow_flow


WORK_POOL_NAME = "orin-shadow-process"
DEPLOYMENT_NAME = "orin-hbstore-shadow"
OWNER_WORK_POOL_NAME = "orin-owner-process"
OWNER_DEPLOYMENT_NAME = "orin-hbstore-owner-commissioning"


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
            OWNER_WORK_POOL_NAME,
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
    subprocess.run(["prefect", "work-pool", "pause", WORK_POOL_NAME], check=True)
    subprocess.run(
        ["prefect", "work-pool", "pause", OWNER_WORK_POOL_NAME], check=True
    )
    asyncio.run(_verify())
    print("ORIN_PREFECT_SHADOW_BOOTSTRAP_OK")


if __name__ == "__main__":
    main()
