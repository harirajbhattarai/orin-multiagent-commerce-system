-- Restore the least-privilege Data API grant required by the client
-- operations dashboard. Row visibility remains tenant-scoped by the existing
-- content_jobs_select_for_members RLS policy.

grant select (client_id, status)
  on table public.content_jobs to authenticated;

