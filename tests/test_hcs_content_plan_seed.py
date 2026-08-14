import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "docs/evidence/2026-08-14-hcs-content-plan-dedup-audit.json"
MIGRATION_PATH = (
    ROOT
    / "supabase/migrations/20260814013612_hcs_deduplicated_content_plan.sql"
)


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _migration_plan() -> list[dict]:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    match = re.search(r"\$hcs_plan\$(\[.*?\])\$hcs_plan\$::jsonb", sql, re.DOTALL)
    assert match is not None
    return json.loads(match.group(1))


def test_hcs_plan_is_complete_ordered_and_unique():
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    items = audit["accepted_items"]

    assert audit["client_id"] == "hcs_gadgets"
    assert audit["accepted_count"] == 30
    assert [item["item_number"] for item in items] == list(range(1, 31))
    assert len({_normalize(item["topic"]) for item in items}) == 30
    assert len({_normalize(item["target_keyword"]) for item in items}) == 30
    assert all(item["target_date"] for item in items)


def test_migration_matches_reviewed_audit_and_keeps_gates_closed():
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    migration_items = _migration_plan()
    audited = {
        item["item_number"]: {
            "target_date": item["target_date"],
            "cluster": item["cluster"],
            "topic": item["topic"],
            "target_keyword": item["target_keyword"],
        }
        for item in audit["accepted_items"]
    }
    migrated = {
        item["item_number"]: {
            "target_date": item["target_date"],
            "cluster": item["cluster"],
            "topic": item["topic"],
            "target_keyword": item["target_keyword"],
        }
        for item in migration_items
    }

    assert migrated == audited
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "client.status = 'maintenance'" in sql
    assert "not settings.request_intake_enabled" in sql
    assert "not settings.automation_enabled" in sql
    assert "not settings.shopify_writes_enabled" in sql
    assert "not settings.approved_draft_writes_enabled" in sql
    assert "settings.allowed_mode = 'dry-run'" in sql
