-- Cover every referencing side of the approval handoff foreign keys. These
-- indexes keep cleanup, reconciliation, and parent-row checks bounded as the
-- handoff ledger grows.

create index client_approval_handoffs_content_item_fk_idx
  on public.client_approval_handoffs(client_id, content_item_id);

create index client_approval_handoffs_decision_fk_idx
  on public.client_approval_handoffs(decision_id)
  where decision_id is not null;

create index client_approval_handoffs_content_job_fk_idx
  on public.client_approval_handoffs(content_job_id)
  where content_job_id is not null;
