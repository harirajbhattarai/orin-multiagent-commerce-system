from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest

from orin_worker.models import ClaimedJob, CompletionRecord
from orin_worker.cli import _capture_review_draft, build_parser, database_url_from_environment
from orin_worker.repository import PostgresWorkerRepository
from orin_worker.service import (
    LeaseLostError,
    ResultContractError,
    work_forever,
    work_once,
)


JOB_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def claimed_job(
    *,
    payload: dict[str, Any] | None = None,
    requested_mode: str = "dry-run",
) -> ClaimedJob:
    return ClaimedJob(
        job_id=JOB_ID,
        client_id="hoverboard_store",
        request_id=REQUEST_ID,
        requested_mode=requested_mode,  # type: ignore[arg-type]
        attempt_count=1,
        payload={} if payload is None else payload,
        lease_expires_at=datetime.now(timezone.utc),
    )


def final_result(**overrides: object) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "orin.final-result/v2",
        "run_id": "hb_20260722T180000Z_12345678",
        "request_id": str(REQUEST_ID),
        "client_id": "hoverboard_store",
        "job_id": None,
        "attempt": 1,
        "requested_mode": "dry-run",
        "effective_mode": "dry-run",
        "status": "completed",
        "decision": "no_job_due",
        "code_version": "test-sha",
        "config_version": None,
        "idempotency_key": f"hoverboard_store:{REQUEST_ID}",
        "replay_disposition": "terminal",
        "shopify_write_state": "not_attempted",
        "shopify_idempotency_marker": None,
        "shopify_article_id": None,
        "shopify_create_count": 0,
        "shopify_published": False,
        "queue_changed": False,
        "reconciliation_status": "not_required",
        "started_at": "2026-07-22T18:00:00+00:00",
        "finished_at": "2026-07-22T18:00:01+00:00",
        "artifact_uri": "/private/evidence/run",
        "error_code": None,
        "pipeline_exit_code": 0,
    }
    result.update(overrides)
    return result


class FakeRepository:
    def __init__(self, job: ClaimedJob | None) -> None:
        self.job = job
        self.claims: list[tuple[str, int]] = []
        self.materializations = 0
        self.renewals: list[tuple[UUID, str, int]] = []
        self.completions: list[dict[str, Any]] = []
        self.deferrals: list[dict[str, Any]] = []
        self.renew_result = True
        self.completion = CompletionRecord(
            run_id="hb_20260722T180000Z_12345678",
            status="completed",
            replayed=False,
        )

    def materialize_next_content_decision(self) -> None:
        self.materializations += 1

    def claim_next(self, *, worker_id: str, lease_seconds: int) -> ClaimedJob | None:
        self.claims.append((worker_id, lease_seconds))
        return self.job

    def renew(self, *, job_id: UUID, worker_id: str, lease_seconds: int) -> bool:
        self.renewals.append((job_id, worker_id, lease_seconds))
        return self.renew_result

    def complete(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        final_result: dict[str, Any],
        review_draft: dict[str, Any] | None = None,
    ) -> CompletionRecord:
        self.completions.append(
            {
                "job_id": job_id,
                "worker_id": worker_id,
                "final_result": final_result,
                "review_draft": review_draft,
            }
        )
        return self.completion

    def defer(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        final_result: dict[str, Any],
    ) -> CompletionRecord:
        self.deferrals.append(
            {"job_id": job_id, "worker_id": worker_id, "final_result": final_result}
        )
        return CompletionRecord(
            run_id=str(final_result["run_id"]),
            status="queued",
            replayed=False,
        )


def test_no_due_job_is_a_successful_noop():
    repository = FakeRepository(None)
    executed = False

    def execute(_: ClaimedJob) -> dict[str, Any]:
        nonlocal executed
        executed = True
        return final_result()

    outcome = work_once(repository, worker_id="worker:test:1", execute=execute)

    assert outcome.to_dict() == {
        "status": "no_job_due",
        "job_id": None,
        "run_id": None,
        "replayed": False,
    }
    assert executed is False
    assert repository.materializations == 1
    assert repository.completions == []


def test_manual_worker_accepts_only_an_iso_as_of_date():
    parsed = build_parser().parse_args(
        ["once", "--client-id", "hoverboard_store", "--as-of-date", "2026-08-08"]
    )
    assert parsed.as_of_date == "2026-08-08"

    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["once", "--client-id", "hoverboard_store", "--as-of-date", "08/08/2026"]
        )


def test_manual_worker_accepts_only_a_positive_job_number():
    parsed = build_parser().parse_args(
        ["once", "--client-id", "hoverboard_store", "--job-number", "029"]
    )
    assert parsed.job_number == "29"

    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["once", "--client-id", "hoverboard_store", "--job-number", "0"]
        )
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["once", "--client-id", "hoverboard_store", "--job-number", "job29"]
        )


def test_worker_requires_an_explicit_supported_client_binding():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["serve", "--worker-id", "orin-hbstore-prod"])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["once", "--client-id", "unknown_client"])


def test_automatic_worker_has_fixed_execution_scope():
    parsed = build_parser().parse_args(
        [
            "serve",
            "--client-id",
            "hoverboard_store",
            "--worker-id",
            "orin-hbstore-prod",
            "--poll-seconds",
            "15",
        ]
    )

    assert parsed.command == "serve"
    assert parsed.worker_id == "orin-hbstore-prod"
    assert parsed.client_id == "hoverboard_store"
    assert parsed.poll_seconds == 15
    assert not hasattr(parsed, "as_of_date")
    assert not hasattr(parsed, "job_number")

    with pytest.raises(SystemExit):
        build_parser().parse_args(["serve", "--job-number", "30"])


def test_dedicated_hcs_worker_has_an_explicit_client_binding():
    parsed = build_parser().parse_args(
        ["serve", "--client-id", "hcs_gadgets", "--worker-id", "orin-hcs-prod"]
    )

    assert parsed.client_id == "hcs_gadgets"
    assert parsed.worker_id == "orin-hcs-prod"
    assert not hasattr(parsed, "as_of_date")
    assert not hasattr(parsed, "job_number")


def test_automatic_worker_stops_after_a_no_job_receipt():
    repository = FakeRepository(None)
    stop_event = threading.Event()
    outcomes = []

    def record_outcome(outcome):
        outcomes.append(outcome)
        stop_event.set()

    work_forever(
        repository,
        worker_id="orin-hbstore-prod",
        execute=lambda _: final_result(),
        stop_event=stop_event,
        poll_interval_seconds=0.01,
        error_backoff_seconds=0.01,
        on_outcome=record_outcome,
    )

    assert [outcome.status for outcome in outcomes] == ["no_job_due"]
    assert repository.claims == [("orin-hbstore-prod", 1200)]


def test_claimed_job_is_completed_with_the_exact_runner_result():
    repository = FakeRepository(claimed_job())
    result = final_result()

    outcome = work_once(
        repository,
        worker_id="worker:test:1",
        execute=lambda _: result,
    )

    assert outcome.status == "completed"
    assert outcome.job_id == str(JOB_ID)
    assert outcome.run_id == result["run_id"]
    assert repository.completions[0]["final_result"] == result


@pytest.mark.parametrize(
    "result",
    [
        final_result(client_id="another_client"),
        final_result(request_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
        final_result(requested_mode="hidden-draft"),
        final_result(shopify_create_count=1),
        final_result(shopify_published=True),
        final_result(queue_changed=True),
    ],
)
def test_mismatched_or_mutating_results_are_never_persisted(result):
    repository = FakeRepository(claimed_job())

    with pytest.raises(ResultContractError):
        work_once(repository, worker_id="worker:test:1", execute=lambda _: result)

    assert repository.completions == []


def test_nonempty_job_payload_is_rejected_before_execution():
    repository = FakeRepository(claimed_job(payload={"command": "anything"}))

    with pytest.raises(ResultContractError, match="empty, supported-mode"):
        work_once(repository, worker_id="worker:test:1", execute=lambda _: final_result())

    assert repository.completions == []


def test_hidden_draft_completion_requires_exact_marker_and_stays_unpublished():
    job = claimed_job(requested_mode="hidden-draft")
    repository = FakeRepository(job)
    result = final_result(
        requested_mode="hidden-draft",
        effective_mode="hidden-draft",
        decision="DRAFT_CREATED_VERIFICATION_PASSED",
        shopify_idempotency_marker=f"orin-v1:hoverboard_store:{REQUEST_ID}",
        shopify_article_id="9001",
        shopify_create_count=1,
        reconciliation_status="reconciled",
        shopify_write_state="article_observed",
    )

    outcome = work_once(repository, worker_id="worker:test:1", execute=lambda _: result)

    assert outcome.status == "completed"
    assert repository.completions[0]["final_result"]["shopify_published"] is False
    assert repository.completions[0]["final_result"]["queue_changed"] is False


def test_approved_review_draft_completion_requires_verified_shopify_handle():
    repository = FakeRepository(claimed_job(requested_mode="hidden-draft"))
    result = final_result(
        requested_mode="hidden-draft",
        effective_mode="hidden-draft",
        decision="APPROVED_REVIEW_DRAFT_CREATED_VERIFICATION_PASSED",
        shopify_idempotency_marker=f"orin-v1:hoverboard_store:{REQUEST_ID}",
        shopify_article_id="9001",
        shopify_create_count=1,
        reconciliation_status="reconciled",
        shopify_write_state="article_observed",
    )

    with pytest.raises(ResultContractError, match="missing its Shopify handle"):
        work_once(repository, worker_id="worker:test:1", execute=lambda _: result)

    assert repository.completions == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"shopify_idempotency_marker": "orin-v1:wrong"},
        {"effective_mode": "live-draft"},
        {"shopify_published": True},
        {"queue_changed": True},
        {"shopify_create_count": 2},
        {"reconciliation_status": "not_started"},
    ],
)
def test_hidden_draft_unsafe_or_unreconciled_results_are_rejected(overrides):
    repository = FakeRepository(claimed_job(requested_mode="hidden-draft"))
    safe_result = {
        "requested_mode": "hidden-draft",
        "effective_mode": "hidden-draft",
        "shopify_idempotency_marker": f"orin-v1:hoverboard_store:{REQUEST_ID}",
        "shopify_article_id": "9001",
        "shopify_create_count": 1,
        "reconciliation_status": "reconciled",
        "shopify_write_state": "article_observed",
    }
    safe_result.update(overrides)
    result = final_result(
        **safe_result,
    )

    with pytest.raises(ResultContractError):
        work_once(repository, worker_id="worker:test:1", execute=lambda _: result)

    assert repository.completions == []


def test_needs_review_is_durably_deferred_instead_of_completed():
    repository = FakeRepository(claimed_job(requested_mode="hidden-draft"))
    result = final_result(
        requested_mode="hidden-draft",
        effective_mode="hidden-draft",
        status="blocked",
        decision="DRAFT_CREATED_VERIFICATION_FAILED",
        replay_disposition="reconcile",
        shopify_write_state="article_observed",
        shopify_idempotency_marker=f"orin-v1:hoverboard_store:{REQUEST_ID}",
        shopify_article_id="9001",
        shopify_create_count=1,
        reconciliation_status="needs_review",
    )

    outcome = work_once(repository, worker_id="worker:test:1", execute=lambda _: result)

    assert outcome.status == "queued"
    assert repository.completions == []
    assert repository.deferrals[0]["final_result"] == result


def test_current_run_draft_capture_is_version_bound_and_private(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    draft = run_dir / "writer_output.html"
    draft.write_text(
        "<!--\n"
        "Meta Title: Safe Scooter Brake Checks for Parents\n"
        "Meta Description: Use this practical pre-ride checklist to inspect a child's electric scooter brakes and know when to stop and seek model-specific support.\n"
        "-->\n"
        "<article><h1>Safe guide</h1><p>Useful parent advice.</p></article>"
    )
    (run_dir / "pipeline_preview.json").write_text(
        '{"writer_output_path": "' + str(draft) + '", "selected_topic": "Safe guide"}'
    )
    result = final_result(
        job_id="33",
        artifact_uri=str(run_dir),
    )
    snapshot = {
        "selected_item_number": 33,
        "items": [
            {
                "item_number": 33,
                "content_item_id": "33333333-3333-4333-8333-333333333333",
                "version": 4,
                "topic": "Safe guide",
            }
        ],
    }

    captured = _capture_review_draft(result, snapshot)

    assert captured is not None
    assert captured["content_item_version"] == 4
    assert captured["title"] == "Safe guide"
    assert captured["word_count"] == 5
    assert captured["meta_title"] == "Safe Scooter Brake Checks for Parents"
    assert captured["meta_description"].startswith("Use this practical pre-ride checklist")
    assert len(str(captured["body_sha256"])) == 64


def test_unknown_hidden_draft_state_requires_reconciliation_not_safe_retry():
    repository = FakeRepository(claimed_job(requested_mode="hidden-draft"))
    result = final_result(
        requested_mode="hidden-draft",
        effective_mode="none",
        status="failed",
        decision="pipeline_timeout",
        replay_disposition="retry",
        shopify_write_state="unknown",
        shopify_idempotency_marker=f"orin-v1:hoverboard_store:{REQUEST_ID}",
        reconciliation_status="needs_review",
    )

    with pytest.raises(ResultContractError, match="safe retry"):
        work_once(repository, worker_id="worker:test:1", execute=lambda _: result)

    assert repository.completions == []
    assert repository.deferrals == []


def test_lost_lease_blocks_finalization():
    repository = FakeRepository(claimed_job())
    repository.renew_result = False

    def slow_result(_: ClaimedJob) -> dict[str, Any]:
        time.sleep(0.03)
        return final_result()

    with pytest.raises(LeaseLostError):
        work_once(
            repository,
            worker_id="worker:test:1",
            execute=slow_result,
            lease_seconds=1,
            heartbeat_interval_seconds=0.01,
        )

    assert repository.renewals
    assert repository.completions == []


class ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one(self) -> object:
        return self.value


class RoleConnection:
    def __init__(self, role: str) -> None:
        self.role = role

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def execute(self, statement: object) -> ScalarResult:
        if str(statement) == "select current_user":
            return ScalarResult(self.role)
        return ScalarResult(1)


class RoleEngine:
    def __init__(self, role: str) -> None:
        self.connection = RoleConnection(role)

    def connect(self) -> RoleConnection:
        return self.connection

    def dispose(self) -> None:
        pass


def test_repository_rejects_an_overprivileged_database_role():
    with pytest.raises(ValueError, match="cannot serve client hoverboard_store"):
        PostgresWorkerRepository(  # type: ignore[arg-type]
            RoleEngine("postgres"),
            expected_role="postgres",
            client_id="hoverboard_store",
        )


def test_repository_accepts_only_the_narrow_worker_role():
    repository = PostgresWorkerRepository(  # type: ignore[arg-type]
        RoleEngine("orin_worker"), client_id="hoverboard_store"
    )

    repository.ping()


def test_repository_rejects_an_unbound_worker():
    with pytest.raises(ValueError, match="explicit supported client"):
        PostgresWorkerRepository(RoleEngine("orin_worker"))  # type: ignore[arg-type]


def test_repository_binds_hcs_to_its_dedicated_role():
    repository = PostgresWorkerRepository(  # type: ignore[arg-type]
        RoleEngine("orin_hcs_worker"),
        expected_role="orin_hcs_worker",
        client_id="hcs_gadgets",
    )

    repository.ping()


def test_repository_binds_hcs_shopify_to_its_approval_only_role():
    repository = PostgresWorkerRepository(  # type: ignore[arg-type]
        RoleEngine("orin_hcs_shopify_worker"),
        expected_role="orin_hcs_shopify_worker",
        client_id="hcs_gadgets",
    )

    repository.ping()


def test_worker_reads_database_url_from_private_file(tmp_path, monkeypatch):
    secret = tmp_path / "database_url"
    secret.write_text("postgresql://orin_worker:secret@example.test/postgres\n")
    secret.chmod(0o400)
    monkeypatch.delenv("ORIN_WORKER_DATABASE_URL", raising=False)
    monkeypatch.setenv("ORIN_WORKER_DATABASE_URL_FILE", str(secret))

    assert database_url_from_environment() == "postgresql://orin_worker:secret@example.test/postgres"


def test_worker_rejects_ambiguous_database_url_sources(tmp_path, monkeypatch):
    secret = tmp_path / "database_url"
    secret.write_text("postgresql://orin_worker:secret@example.test/postgres\n")
    secret.chmod(0o400)
    monkeypatch.setenv("ORIN_WORKER_DATABASE_URL", "postgresql://direct")
    monkeypatch.setenv("ORIN_WORKER_DATABASE_URL_FILE", str(secret))

    with pytest.raises(ValueError, match="exactly one"):
        database_url_from_environment()
