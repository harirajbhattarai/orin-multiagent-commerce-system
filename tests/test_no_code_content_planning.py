from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260826170000_no_code_content_planning.sql"


def test_no_code_planner_is_member_scoped_and_fail_closed():
    sql = MIGRATION.read_text()

    assert "membership.role in ('owner', 'operator')" in sql
    assert "status = 'planned'" not in sql  # insert uses a literal, not a gate mutation
    assert "'planned'" in sql
    assert "insert into public.content_jobs" not in sql
    assert "client_runtime_settings" not in sql
    assert "scheduler_health" not in sql
    assert "shopify" in sql.lower()
    assert "grant execute on function public.plan_next_content_article" in sql


def test_no_code_planner_deduplicates_title_and_keyword():
    sql = MIGRATION.read_text()

    assert "an article with this title is already planned" in sql
    assert "an article with this target keyword is already planned" in sql
    assert "pg_advisory_xact_lock" in sql
