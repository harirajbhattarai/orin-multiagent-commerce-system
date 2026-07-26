from pathlib import Path


WORKSPACE_TEMPLATE = Path("deploy/openclaw/orin-hbstore-prod")
REQUIRED_FILES = {"SOUL.md", "IDENTITY.md", "TOOLS.md", "MEMORY.md", "RUNBOOK.md"}


def test_hbstore_agent_has_complete_isolated_boundary_files():
    assert {path.name for path in WORKSPACE_TEMPLATE.iterdir()} == REQUIRED_FILES

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
        path.read_text(encoding="utf-8") for path in WORKSPACE_TEMPLATE.iterdir()
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
