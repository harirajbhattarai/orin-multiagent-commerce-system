"""Prefect flow that records a read-only ORIN planner prediction."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from prefect import flow, get_run_logger
from prefect.artifacts import create_markdown_artifact

from .predictor import FIXED_CLIENT_ID, predict_shadow_run
from .repository import ShadowRepository


@flow(
    name="orin-hbstore-shadow",
    description="Read-only ORIN planner shadow; never creates jobs or Shopify writes.",
    log_prints=True,
    retries=0,
    persist_result=False,
)
def hbstore_shadow_flow(as_of_date: str | None = None) -> dict[str, object]:
    business_date = (
        date.fromisoformat(as_of_date)
        if as_of_date is not None
        else datetime.now(ZoneInfo("Europe/London")).date()
    )
    database_url_file = Path(
        os.environ.get(
            "ORIN_PREFECT_SHADOW_DATABASE_URL_FILE",
            "/run/secrets/shadow_database_url",
        )
    )
    expected_role = os.environ.get(
        "ORIN_PREFECT_SHADOW_DATABASE_ROLE", "orin_prefect_shadow"
    )
    repository = ShadowRepository(database_url_file, expected_role=expected_role)
    snapshot = repository.snapshot(client_id=FIXED_CLIENT_ID)
    prediction = predict_shadow_run(snapshot, as_of_date=business_date)
    rendered = json.dumps(prediction, sort_keys=True, indent=2)
    get_run_logger().info("ORIN_PREFECT_SHADOW_RESULT %s", rendered)
    create_markdown_artifact(
        key="orin-hbstore-shadow-latest",
        description="Latest read-only Prefect shadow prediction for Hoverboard Store.",
        markdown=f"```json\n{rendered}\n```",
    )
    return prediction
