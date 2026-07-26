create or replace function orin_private.normalize_hoverboard_scheduler_payload()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
  if new.client_id = 'hoverboard_store'
     and new.requested_by is null
     and new.requested_mode in ('dry-run', 'hidden-draft')
     and new.source_job_key ~ '^scheduler:orin-hbstore-prod:[0-9]{4}-[0-9]{2}-[0-9]{2}$'
     and new.payload = jsonb_build_object(
       'scheduler_owner', 'openclaw:orin-hbstore-prod',
       'schedule', 'daily-1100-europe-london',
       'schedule_date', split_part(new.source_job_key, ':', 3)
     ) then
    new.payload := '{}'::jsonb;
  end if;
  return new;
end;
$$;

revoke all on function orin_private.normalize_hoverboard_scheduler_payload()
from public, anon, authenticated, orin_api, orin_worker, orin_scheduler;

drop trigger if exists normalize_hoverboard_scheduler_payload
on public.content_jobs;

create trigger normalize_hoverboard_scheduler_payload
before insert or update of client_id, source_job_key, requested_by, requested_mode, payload
on public.content_jobs
for each row
execute function orin_private.normalize_hoverboard_scheduler_payload();

update public.content_jobs
set payload = '{}'::jsonb
where client_id = 'hoverboard_store'
  and requested_by is null
  and requested_mode in ('dry-run', 'hidden-draft')
  and source_job_key ~ '^scheduler:orin-hbstore-prod:[0-9]{4}-[0-9]{2}-[0-9]{2}$'
  and payload = jsonb_build_object(
    'scheduler_owner', 'openclaw:orin-hbstore-prod',
    'schedule', 'daily-1100-europe-london',
    'schedule_date', split_part(source_job_key, ':', 3)
  );

comment on function orin_private.normalize_hoverboard_scheduler_payload() is
'Normalizes the only legacy fixed scheduler provenance shape to an empty worker-compatible payload.';
