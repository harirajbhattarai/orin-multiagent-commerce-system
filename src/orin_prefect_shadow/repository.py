"""Narrow read-only repository for the Prefect shadow flow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg


class ShadowRepository:
    def __init__(self, database_url_file: Path, *, expected_role: str) -> None:
        self.database_url_file = database_url_file
        self.expected_role = expected_role

    def snapshot(self, *, client_id: str) -> dict[str, Any]:
        database_url = self.database_url_file.read_text(encoding="utf-8").strip()
        if not database_url:
            raise RuntimeError("shadow database URL file is empty")
        with psycopg.connect(database_url, autocommit=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select current_user")
                current_role = cursor.fetchone()[0]
                if current_role != self.expected_role:
                    raise RuntimeError(
                        "database role mismatch: "
                        f"required={self.expected_role}, received={current_role}"
                    )
                cursor.execute(
                    "select orin_private.get_prefect_shadow_snapshot(%s)",
                    (client_id,),
                )
                value = cursor.fetchone()[0]
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            raise RuntimeError("shadow snapshot function returned a non-object")
        return value
