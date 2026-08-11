"""One-shot Prefect flow for the controlled scheduler ownership proof."""

from __future__ import annotations

import json
import os
from pathlib import Path

from prefect import flow, get_run_logger
from prefect.artifacts import create_markdown_artifact

from .repository import OwnerRepository


@flow(
    name="orin-hbstore-owner-commissioning",
    description="One fixed-client dry-run enqueue; never receives Shopify credentials.",
    log_prints=True,
    retries=0,
    persist_result=False,
)
def hbstore_owner_commissioning_flow() -> dict[str, object]:
    database_url_file = Path(
        os.environ.get(
            "ORIN_PREFECT_OWNER_DATABASE_URL_FILE",
            "/run/secrets/owner_database_url",
        )
    )
    expected_role = os.environ.get(
        "ORIN_PREFECT_OWNER_DATABASE_ROLE", "orin_prefect_scheduler"
    )
    receipt = OwnerRepository(
        database_url_file, expected_role=expected_role
    ).enqueue().as_json()
    result: dict[str, object] = {
        "schema": "orin.prefect-owner-commissioning/v1",
        "status": "accepted",
        **receipt,
    }
    rendered = json.dumps(result, sort_keys=True, indent=2)
    get_run_logger().info("ORIN_PREFECT_OWNER_RESULT %s", rendered)
    create_markdown_artifact(
        key="orin-hbstore-owner-commissioning",
        description="Controlled dry-run Prefect scheduler ownership receipt.",
        markdown=f"```json\n{rendered}\n```",
    )
    return result
