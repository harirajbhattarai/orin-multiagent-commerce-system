-- Make the deny-by-default customer boundary explicit and cover the composite
-- content_jobs foreign key used during parent-row updates and deletes.

create policy job_attempts_deny_customer_access
on public.job_attempts
for all
to anon, authenticated
using (false)
with check (false);

create index job_attempts_client_job_idx
  on public.job_attempts(client_id, job_id);
