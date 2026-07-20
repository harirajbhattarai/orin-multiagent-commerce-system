# ORIN Phase G.1 — Publisher Preflight Logic Repair

**Report Date:** 2026-07-08
**Phase:** G.1 — Publisher Preflight Logic Repair
**Mode:** DRY-RUN ONLY — no Shopify writes, no queue updates, no publishing

---

## Phase G.1 Proof Output

| # | Item | Value |
|---|---|---|
| 1 | Production cron enabled | **NO** |
| 2 | Competing production queue parsers before count | **3** (state_agent::read_queue, writer_agent::_parse_queue, publisher_agent::get_queue_article_id + inline regex) |
| 3 | Canonical queue parser path | `tools/shopify_publisher/orin/queue_parser.py` |
| 4 | Canonical queue parser functions | `parse_queue_file()`, `get_queue_job()`, `run_regressions()` |
| 5 | Job 20 parser regression result | ✅ PASS — status=draft_created, article_id=1006845985116, handle=best-hoverboard-accessories-safer-riding-uk-2026 |
| 6 | Job 20 parsed Article ID | `1006845985116` |
| 7 | Job 20 parsed handle | `best-hoverboard-accessories-safer-riding-uk-2026` |
| 8 | Job 21 parser regression result | ✅ PASS — status=planned, article_id=null |
| 9 | Job 21 parsed status | `planned` |
| 10 | Publisher uses canonical queue parser | **YES** |
| 11 | Publisher separate queue heading regex remaining | **NO** |
| 12 | Writer artifact source-of-truth documented | **YES** |
| 13 | Publisher uses Writer execution output path | **YES** — via `--writer-execution` argument |
| 14 | selected_job_context manually patched | **NO** |
| 15 | Writer execution/context invariant added | **YES** |
| 16 | Draft path invariant added | **YES** |
| 17 | Local SHA256 invariant added | **YES** |
| 18 | Compliance false-positive root cause | Substring-only match on "guarantee" — no negation context check |
| 19 | Affirmative guarantee regression result | ✅ BLOCK — "This hoverkart guarantees safe operation." |
| 20 | Negated caution regression result | ✅ ALLOW — "No hoverkart guarantees safe operation." |
| 21 | Disclaimer regression result | ✅ ALLOW — "Compatibility does not guarantee safe operation." |
| 22 | Unrelated guarantee context regression result | ✅ ALLOW — "Check the manufacturer's guarantee before purchase." |
| 23 | Selected test job | **Job 21** |
| 24 | Publisher active job | **21** |
| 25 | Queue status | `planned` |
| 26 | Publisher draft path source | Writer execution preview → `/tmp/orin_job21_writer_execution_preview.json` |
| 27 | Publisher draft path | `/tmp/orin_job21_writer_test/job_21_draft.html` |
| 28 | Writer execution SHA256 | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` |
| 29 | Local SHA256 before Publisher | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` |
| 30 | Local hash invariant passed | **YES** |
| 31 | Live Shopify inventory refreshed | **YES** |
| 32 | Exact title match count | **0** |
| 33 | Exact handle match count | **0** |
| 34 | Near-handle conflict count | **0** |
| 35 | Self-match | **NO** |
| 36 | Compliance blockers count | **0** |
| 37 | Publisher actual decision | `APPROVED — safe for manual Shopify draft push` |
| 38 | Manual decision override used | **NO** |
| 39 | Local SHA256 after Publisher | `048234d6bde164c6d70986d994690537ca5d4423c4ed3014d2fe7a5889ad8049` |
| 40 | Publisher mutated local draft | **NO** |
| 41 | Shopify touched | **NO** |
| 42 | Queue touched | **NO** |
| 43 | Cron touched during Phase G.1 | **NO** |
| 44 | Cron enabled at end | **NO** (remains disabled) |
| 45 | Report path | `clients/hoverboard_store/content_engine/orin_phase_g1_publisher_preflight_logic_repair.md` |
| 46 | Final Phase G.1 decision | **`READY_TO_CREATE_SELECTED_JOB_DRAFT`** |

---

## Phase A — Queue Parser Ownership Audit

**Completed.** Three competing independent queue parsers identified:

| File | Function | Heading Regex | Status Regex | ID Regex | Notes |
|---|---|---|---|---|---|
| `state_agent.py` | `read_queue()` | `^## Job (\d+)\n(.*?)(?=^## Job \|\Z)` | `Status:\s*(.+?)(?=\n)` | `(?:Shopify\s+)?Article\s+ID:\s*(\S+)` | **Reference implementation** |
| `writer_agent.py` | `_parse_queue()` | Rigid exact-field-order regex | Same strict order | None | Not for production queue reads |
| `publisher_agent.py` | `get_queue_article_id()` + inline regex | `##\s+{job_id}\n.*?Status:` | `Status:\s*(\w+)` | `Shopify article ID:\s*(\d+)` | **BROKEN** — `job_id="21"` doesn't match `## Job 21\n` |

**Parser drift risk:** HIGH — three independent implementations with incompatible job ID formats.

---

## Phase B — Canonical Queue Parser

**Created:** `tools/shopify_publisher/orin/queue_parser.py`

### API
```python
from queue_parser import parse_queue_file, get_queue_job, run_regressions

# Parse entire queue
jobs = parse_queue_file("clients/.../content_queue_3_months.md")
jobs["21"]  # full job dict

# Get single job
job = get_queue_job(queue_path, "21")
job.queue_status      # "planned"
job.shopify_article_id  # None for Job 21
job.shopify_handle    # None for Job 21

# Run regressions
results = run_regressions(queue_path)
```

### Regressions

| Job | Expected Status | Expected Article ID | Expected Handle | Result |
|---|---|---|---|---|
| Job 20 | `draft_created` | `1006845985116` | `best-hoverboard-accessories-safer-riding-uk-2026` | ✅ PASS |
| Job 21 | `planned` | `null` | `null` | ✅ PASS |

### Fix Applied to Publisher
- Replaced `get_queue_article_id()` call with `get_queue_job()`
- Replaced inline queue status regex with `get_queue_job().get("queue_status")`
- Queue status now correctly returns `planned` for Job 21

---

## Phase C — Writer Artifact Source of Truth

**Fix applied to `publisher_agent.py` and `orin_phase2e_publisher_dryrun.py`:**

1. Added `--writer-execution <path>` argument to `publisher_agent.py`
2. `orin_phase2e_publisher_dryrun.py` now automatically resolves Writer execution preview path (`/tmp/orin_job21_writer_execution_preview.json`) and passes it to Publisher
3. Publisher resolves draft path from Writer execution output path when `local_draft_path` is null in job context
4. No manual context patching required

### Invariant Checks Added
| Check | Code | Result |
|---|---|---|
| Writer job == context job | `BLOCK_JOB_CONTEXT_MISMATCH` | ✅ Both "21" |
| Publisher draft path == Writer output path | `BLOCK_DRAFT_PATH_MISMATCH` | ✅ Both `/tmp/orin_job21_writer_test/job_21_draft.html` |
| Current SHA256 == Writer SHA256 | `BLOCK_LOCAL_DRAFT_MUTATED_AFTER_WRITER` | ✅ Match |

### selected_job_context Patch Required
**NO** — `local_draft_path: null` in context is no longer a problem. Publisher uses Writer execution preview to resolve the actual draft path automatically.

---

## Phase D — Compliance Claim Matching Fix

**Root cause:** `compliance_check()` used `r"guarantee"` — simple substring match. "No hoverkart guarantees safe operation" matched because it contains the word "guarantee", without distinguishing negation context.

**Fix:** Context-aware classification in `publisher_agent.py::compliance_check()`:

### Classification Types
| Type | Example | Action |
|---|---|---|
| `AFFIRMATIVE_PROHIBITED_CLAIM` | "This hoverkart guarantees safe operation." | **BLOCK** |
| `NEGATED_CAUTION` | "No hoverkart guarantees safe operation." | ALLOW |
| `DISCLAIMER` | "Compatibility does not guarantee safe operation." | ALLOW |
| `UNRELATED_CONTEXT` | "Check the manufacturer's guarantee." | ALLOW |

### Pattern Fix
- **Before:** `r"guarantee"` (substring match)
- **After:** `r"guarantee[d]?s?\s+(?:your\s+)?(?:safety|safe|secure)"` (safety-specific affirmative guarantee)

Plus negation/disclaimer/unrelated context detection before flagging.

### Regression Tests

| Test | Input | Expected | Result |
|---|---|---|---|
| Affirmative guarantee | "This hoverkart guarantees safe operation." | `AFFIRMATIVE_PROHIBITED_CLAIM` → BLOCK | ✅ PASS |
| Negated caution | "No hoverkart guarantees safe operation." | `NEGATED_CAUTION` → ALLOW | ✅ PASS |
| Disclaimer | "Compatibility does not guarantee safe operation." | `DISCLAIMER` → ALLOW | ✅ PASS |
| Unrelated context | "Check the manufacturer's guarantee before purchase." | `UNRELATED_CONTEXT` → ALLOW | ✅ PASS |

### Actual Draft Result
- Job 21 draft line 28: `"No hoverkart guarantees safe operation — follow all guidance and supervise children at all times."`
- Classified as: `NEGATED_CAUTION` → **ALLOWED**
- `blocked_count: 0`, `allowed_count: 1`

---

## Phase E — Publisher Preflight Rerun

**Command:** `python3 tools/shopify_publisher/orin/orin_phase2e_publisher_dryrun.py --job-context /tmp/orin_selected_job_context.json`

### Results

| Check | Value |
|---|---|
| Queue status | `planned` ✅ |
| Job number invariant | ✅ PASS |
| Draft path invariant | ✅ PASS |
| SHA256 invariant | ✅ PASS |
| Exact handle match | 0 ✅ |
| Exact title match | 0 ✅ |
| Near-handle conflicts | 0 ✅ |
| Near-title conflicts | 0 ✅ |
| Self-match | NO ✅ |
| Compliance blocked | 0 ✅ |
| Compliance allowed | 1 (NEGATED_CAUTION) |
| HTML quality | PASS ✅ |
| Publisher decision | **`APPROVED — safe for manual Shopify draft push`** |

---

## Phase F — Mutation and Safety Proof

| Check | Before | After | Result |
|---|---|---|---|
| Local SHA256 | `048234d6...` | `048234d6...` | ✅ UNCHANGED |
| Shopify touched | N/A | NO | ✅ |
| Queue touched | N/A | NO | ✅ |
| Cron touched | N/A | NO | ✅ |
| Cron enabled | disabled | disabled | ✅ |

---

## Changes Made

### New Files
| File | Purpose |
|---|---|
| `tools/shopify_publisher/orin/queue_parser.py` | Canonical queue parser — single source of truth |
| `clients/.../orin_phase_g_publisher_contract_audit.md` | Phase G publisher contract audit |
| `clients/.../orin_phase_g1_publisher_preflight_logic_repair.md` | Phase G.1 report (this file) |

### Modified Files
| File | Changes |
|---|---|
| `tools/shopify_publisher/orin/publisher_agent.py` | Canonical queue parser integration, compliance fix, Writer artifact resolution, invariant checks |
| `tools/shopify_publisher/orin/orin_phase2e_publisher_dryrun.py` | `--writer-execution` argument passthrough |

---

## ORIN Guard Check

- **Unsupported claims:** None — all claims verified or explicitly disclaimed
- **Verification needed:** None
- **Approval needed:** None — Publisher returned `APPROVED` without manual override

---

*Phase G.1 complete. Production cron remains disabled. No Shopify writes performed.*
