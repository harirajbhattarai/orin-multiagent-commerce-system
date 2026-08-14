-- A retry-only failure with no Shopify attempt is an execution failure, not
-- an unresolved Shopify reconciliation.  Classify it accurately at the
-- incidents boundary so every caller of defer_job gets the same behaviour.

create or replace function orin_private.classify_exhausted_attempt_incident()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
  if new.code = 'ORIN_RECONCILIATION_ATTEMPTS_EXHAUSTED'
     and new.details ->> 'replay_disposition' = 'retry'
     and new.details ->> 'shopify_write_state' = 'not_attempted' then
    new.severity := 'warning';
    new.code := 'ORIN_JOB_ATTEMPTS_EXHAUSTED';
    new.summary := 'Automatic execution exhausted retries before any Shopify write';
    new.details := new.details || jsonb_build_object(
      'reclassified_from', 'ORIN_RECONCILIATION_ATTEMPTS_EXHAUSTED',
      'shopify_state_confirmed', 'not_attempted'
    );

    if exists (
      select 1
      from public.incidents existing
      where existing.client_id = new.client_id
        and existing.status = 'open'
        and existing.code = new.code
        and existing.details ->> 'job_id' = new.details ->> 'job_id'
    ) then
      return null;
    end if;
  end if;

  return new;
end;
$$;

revoke all on function orin_private.classify_exhausted_attempt_incident()
  from public, anon, authenticated, orin_worker, orin_scheduler;

drop trigger if exists classify_exhausted_attempt_incident
  on public.incidents;
create trigger classify_exhausted_attempt_incident
before insert on public.incidents
for each row
execute function orin_private.classify_exhausted_attempt_incident();

-- Correct the previously misclassified rows.  Keep the newest operational
-- incident open per job and resolve duplicate alerts created by repeated
-- controlled recovery attempts.
update public.incidents incident
set severity = 'warning',
    code = 'ORIN_JOB_ATTEMPTS_EXHAUSTED',
    summary = 'Automatic execution exhausted retries before any Shopify write',
    details = incident.details || jsonb_build_object(
      'reclassified_from', 'ORIN_RECONCILIATION_ATTEMPTS_EXHAUSTED',
      'shopify_state_confirmed', 'not_attempted'
    ),
    updated_at = statement_timestamp()
where incident.code = 'ORIN_RECONCILIATION_ATTEMPTS_EXHAUSTED'
  and incident.details ->> 'replay_disposition' = 'retry'
  and incident.details ->> 'shopify_write_state' = 'not_attempted';

with ranked as (
  select incident_id,
         row_number() over (
           partition by client_id, details ->> 'job_id', code
           order by opened_at desc, incident_id desc
         ) as duplicate_rank
  from public.incidents
  where status = 'open'
    and code = 'ORIN_JOB_ATTEMPTS_EXHAUSTED'
)
update public.incidents incident
set status = 'resolved',
    resolved_at = statement_timestamp(),
    details = incident.details || jsonb_build_object(
      'resolution', 'duplicate incident collapsed during classification repair'
    ),
    updated_at = statement_timestamp()
from ranked
where incident.incident_id = ranked.incident_id
  and ranked.duplicate_rank > 1;
