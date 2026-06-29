-- =====================================================================
-- AP Exception Handling Agent — RUN STORE table
-- =====================================================================
-- This is the table `SupabaseRunStore` (app/api/supabase_store.py) reads and
-- writes. It is SEPARATE from schema.sql's normalized 9-table model: the run
-- store persists each run as a SINGLE row — indexed scalar columns for
-- listing/filtering plus a JSONB `state` column holding the full serialized
-- RunState — and the app writes to it on EVERY pipeline step whenever
-- SUPABASE_URL + SUPABASE_KEY are configured.
--
-- Columns mirror app/api/supabase_store.py::_row_payload exactly.
--
-- Run this in the Supabase SQL Editor (Database → SQL Editor → New query).
-- Override the table name with SUPABASE_RUNS_TABLE if you don't use "runs".
-- =====================================================================

create table if not exists public.runs (
    run_id           text primary key,
    tenant_id        text,
    status           text,
    current_node     text,
    created_at       timestamptz,
    completed_at     timestamptz,
    rows_accepted    integer default 0,
    rows_quarantined integer default 0,
    state            jsonb not null
);

create index if not exists ix_runs_tenant_id on public.runs (tenant_id);
create index if not exists ix_runs_status     on public.runs (status);
create index if not exists ix_runs_created_at on public.runs (created_at desc);

-- RLS: this table is server-only. The backend MUST use the SERVICE_ROLE key,
-- which bypasses RLS. Enabling RLS with no policies (below) correctly blocks
-- the publishable/anon key — which is why writes with that key fail. Use the
-- service_role key in SUPABASE_KEY and you're done.
alter table public.runs enable row level security;
