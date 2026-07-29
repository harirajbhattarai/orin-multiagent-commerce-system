from pathlib import Path


WORKSPACE_TEMPLATE = Path("deploy/openclaw/orin-hbstore-prod")
WATCHDOG_TEMPLATE = Path("deploy/openclaw/orin-watchdog")
REQUIRED_FILES = {"SOUL.md", "IDENTITY.md", "TOOLS.md", "MEMORY.md", "RUNBOOK.md"}


def test_hbstore_agent_has_complete_isolated_boundary_files():
    assert {
        path.name for path in WORKSPACE_TEMPLATE.iterdir() if path.is_file()
    } == REQUIRED_FILES
    assert (
        WORKSPACE_TEMPLATE / "bin" / "orin_hbstore_trigger.py"
    ).is_file()

    combined = "\n".join(
        (WORKSPACE_TEMPLATE / name).read_text(encoding="utf-8")
        for name in sorted(REQUIRED_FILES)
    )
    required_statements = (
        "Hoverboard Store only",
        "read-only commissioning",
        "Production execution: disabled",
        "Scheduler ownership: none",
        "Shopify publishing: prohibited",
        "general shell",
        "tenant-scoped request",
        "final_result.json",
    )
    for statement in required_statements:
        assert statement in combined


def test_hbstore_agent_template_contains_no_secret_values():
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in WORKSPACE_TEMPLATE.rglob("*")
        if path.is_file() and path.suffix in {".md", ".py"}
    ).lower()
    forbidden_fragments = (
        "sk-cp",
        "shpat_",
        "postgresql://",
        "supabase.co:5432",
        "access_token=",
        "password=",
    )
    for fragment in forbidden_fragments:
        assert fragment not in combined


def test_watchdog_agent_has_complete_read_only_boundary_files():
    assert {
        path.name for path in WATCHDOG_TEMPLATE.iterdir() if path.is_file()
    } == REQUIRED_FILES
    assert (
        WATCHDOG_TEMPLATE / "bin" / "orin_watchdog_check.py"
    ).is_file()

    combined = "\n".join(
        (WATCHDOG_TEMPLATE / name).read_text(encoding="utf-8")
        for name in sorted(REQUIRED_FILES)
    )
    required_statements = (
        "Hoverboard Store only",
        "read-only",
        "disabled",
        "accepts no arguments",
        "database credential",
        "Never create, claim, retry, reconcile, publish, or modify work",
    )
    for statement in required_statements:
        assert statement in combined


def test_watchdog_agent_template_contains_no_secret_values():
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in WATCHDOG_TEMPLATE.rglob("*")
        if path.is_file() and path.suffix in {".md", ".py"}
    ).lower()
    forbidden_fragments = (
        "sk-cp",
        "shpat_",
        "postgresql://",
        "supabase.co:5432",
        "access_token=",
        "password=",
    )
    for fragment in forbidden_fragments:
        assert fragment not in combined
