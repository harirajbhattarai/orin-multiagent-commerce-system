alter table public.client_runtime_settings
add column request_intake_enabled boolean not null default false;
