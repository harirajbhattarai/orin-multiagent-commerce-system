-- Cover recurring-pilot foreign keys used during operator cleanup and audit lookup.

create index client_recurring_pilot_last_job_fk_idx
  on public.client_recurring_pilot_schedules(client_id, last_enqueued_job_id)
  where last_enqueued_job_id is not null;

create index client_recurring_pilot_activated_by_fk_idx
  on public.client_recurring_pilot_schedules(activated_by);
