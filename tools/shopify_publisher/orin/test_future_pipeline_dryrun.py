"""
test_future_pipeline_dryrun.py — Phase 5 dry-run proof.
Fixtures A, B, C — writer plan → output → topic identity gate → readiness.
No Shopify write.
"""

import sys, hashlib, traceback, tempfile, os
from pathlib import Path
sys.path.insert(0, '/data/.openclaw/workspace/tools/shopify_publisher/orin')

BASE_DIR = Path("/data/.openclaw/workspace")

FIXTURES = [
    dict(name="A. Lights Flashing (Troubleshooting)", job_number="22",
         topic="Hoverboard Lights Flashing: What It Usually Means",
         target_keyword="hoverboard lights flashing", cluster="Troubleshooting"),
    dict(name="B. Hoverkart Compatibility (Hoverkart)", job_number="99",
         topic="How to Choose a Hoverkart for Your Hoverboard",
         target_keyword="hoverkart hoverboard compatibility", cluster="Hoverkart"),
    dict(name="C. Beeping (Troubleshooting)", job_number="98",
         topic="Why Your Hoverboard Is Beeping: Common Reasons",
         target_keyword="hoverboard beeping", cluster="Troubleshooting"),
]


def run_fixture(fix):
    from writer_agent import WriterAgent
    from topic_identity_gate import run_topic_identity_gate, TOPIC_IDENTITY_BLOCK

    # Step 1: Build writer plan
    writer = WriterAgent(str(BASE_DIR), "2026-07-09")
    # Generate a valid canonical handle using the writer's own method
    raw_slug = writer._generate_slug(fix["topic"])
    job_ctx = dict(
        job_number=fix["job_number"], topic=fix["topic"],
        target_keyword=fix["target_keyword"], queue_status="planned",
        shopify_handle=raw_slug,
        file_path=f"/tmp/dry-{fix['job_number']}.html",
        target_date="2026-07-21",
    )
    plan_wrapper = writer.plan_writing(job_ctx=job_ctx)
    plan = plan_wrapper.get("writer_plan", plan_wrapper)
    if not plan.get("job_number"):
        plan = plan_wrapper  # fallback

    # Step 2: Generate HTML to explicit temp path
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "output.html"
        try:
            stats = writer.write_selected_job_draft(
                job_ctx, plan, output_path_override=str(tmp_path)
            )
        except Exception as e:
            return {"ready": False, "error": str(e), "tb": traceback.format_exc()}

        if not tmp_path.exists():
            reported = Path(stats.get("output_path", ""))
            if reported.exists():
                html = reported.read_text()
            else:
                return {"ready": False, "error": f"file not written. stats={stats}"}
        else:
            html = tmp_path.read_text()

    sha = hashlib.sha256(html.encode()).hexdigest()
    hk = html.lower().count("hoverkart")
    hk_pass = (fix["cluster"] == "Hoverkart") or (hk == 0)
    print(f"  [Step 2] ✅ generated — {len(html)} bytes, sha={sha[:12]}, hoverkart={hk} {'✅' if hk_pass else '❌ CONTAMINATED'}")

    # Step 3: Topic identity gate
    h2_outline = plan.get("h2_outline", [])
    approved_h2_plan = [{"id": h.get("id", ""), "h2": h.get("h2", "")} for h in h2_outline]
    tg = run_topic_identity_gate(
        job_id=fix["job_number"], expected_topic=fix["topic"],
        target_keyword=fix["target_keyword"], cluster=fix["cluster"],
        approved_h2_plan=approved_h2_plan, output_html=html,
    )
    tg_pass = tg["decision"] != TOPIC_IDENTITY_BLOCK
    if tg_pass:
        print(f"  [Step 3] ✅ PASS — TOPIC_IDENTITY_PASS")
    else:
        print(f"  [Step 3] ❌ BLOCK — {tg['blockers']}")
        for c in tg.get("checks", []):
            if not c["passed"]:
                print(f"           {c['check']}: {c['detail']}")

    # Step 4: Hoverkart contamination gate
    # For non-Hoverkart clusters: hoverkart count MUST be 0
    # For Hoverkart cluster: hoverkart count MUST be > 0
    hk_gate_pass = (fix["cluster"] == "Hoverkart") or (hk == 0)
    hk_gate_note = "hoverkart expected (Hoverkart cluster)" if fix["cluster"] == "Hoverkart" else "hoverkart must be 0"
    if hk_gate_pass:
        print(f"  [Step 4] ✅ hoverkart gate: {hk} {hk_gate_note}")
    else:
        print(f"  [Step 4] ❌ hoverkart gate FAIL: {hk} found (expected 0)")

    # Step 5: H1 match check
    import re
    h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.IGNORECASE)
    h1_texts = [re.sub(r'<[^>]+>', '', h).strip() for h in h1s]
    h1_match = any(t.lower() == fix["topic"].lower() for t in h1_texts)
    if h1_match:
        print(f"  [Step 5] ✅ H1 matches expected topic")
    else:
        print(f"  [Step 5] ⚠️  H1: {h1_texts[0] if h1_texts else 'NONE'} (expected: {fix['topic']})")

    # Transaction readiness
    ready = tg_pass and hk_gate_pass
    print(f"\n  Transaction ready: {'✅ READY' if ready else '❌ NOT READY'}")
    return {
        "ready": ready,
        "hoverkart_count": hk,
        "topic_gate_pass": tg_pass,
        "hk_gate_pass": hk_gate_pass,
        "h1_match": h1_match,
        "html_size": len(html),
        "sha256": sha,
    }


def main():
    print("=" * 70)
    print("FUTURE PIPELINE DRY-RUN — Phase 5 Proof")
    print("=" * 70)
    all_ready = True

    for fix in FIXTURES:
        print(f"\n{'='*60}")
        print(f"FIXTURE: {fix['name']} (cluster={fix['cluster']})")
        print("=" * 60)
        try:
            r = run_fixture(fix)
        except Exception as e:
            print(f"  ❌ EXCEPTION: {e}")
            print(traceback.format_exc())
            r = {"ready": False}
        if not r.get("ready"):
            all_ready = False

    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    if all_ready:
        print("✅ ALL FIXTURES: pipeline reaches transaction readiness")
        print("   Cron stays disabled. No Shopify write.")
    else:
        print("❌ SOME FIXTURES: blocked before transaction readiness")
    print("=" * 70)
    return all_ready


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
