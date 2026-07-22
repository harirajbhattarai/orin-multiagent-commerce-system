create index runs_job_fk_idx
  on public.runs(client_id, job_id)
  where job_id is not null;

create index incidents_run_fk_idx
  on public.incidents(client_id, run_id)
  where run_id is not null;

create index scheduler_health_last_run_fk_idx
  on public.scheduler_health(client_id, last_observed_run_id)
  where last_observed_run_id is not null;
