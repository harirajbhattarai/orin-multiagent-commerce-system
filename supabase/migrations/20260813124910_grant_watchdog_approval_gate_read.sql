-- Keep the fixed-client read-only watchdog compatible with the approval-only
-- hidden-draft gate added in Phase 6. The watchdog repository includes this
-- column in its scheduler-safety snapshot but receives no mutation privilege.

grant select (approved_draft_writes_enabled)
on table public.client_runtime_settings to orin_watchdog;

comment on role orin_watchdog is
  'NOLOGIN read-only HBStore scheduler observation role, including the approval-only gate';
