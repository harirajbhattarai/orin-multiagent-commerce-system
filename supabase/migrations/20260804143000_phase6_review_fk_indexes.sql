-- Cover the composite foreign keys introduced by the durable review workflow.
-- These indexes keep parent-row updates and deletes from scanning the child
-- tables as review history grows.

create index if not exists content_decisions_content_job_fk_idx
  on public.content_decisions(client_id, content_job_id)
  where content_job_id is not null;

create index if not exists content_drafts_source_run_fk_idx
  on public.content_drafts(client_id, source_run_id);
