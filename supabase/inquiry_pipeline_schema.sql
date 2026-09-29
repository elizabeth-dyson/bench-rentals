-- Phase 5.3 INSTALL 1/2. Pending user installation and database verification.
-- Run inspect_inquiry_schema.sql first; requires the installed Phase 5.1 baseline.
-- Use an isolated project first. No business rows are created or backfilled.
begin;

create schema if not exists inquiry_private;
revoke all on schema inquiry_private from public, anon, authenticated, service_role;

alter table public.intake_submissions
    add column if not exists request_id uuid,
    add column if not exists request_fingerprint text,
    add column if not exists customer_match_outcome text;

do $$
begin
    if not exists (select 1 from pg_constraint where conrelid = 'public.intake_submissions'::regclass
                   and conname = 'intake_submissions_request_id_key') then
        alter table public.intake_submissions add constraint intake_submissions_request_id_key unique(request_id);
    end if;
    if not exists (select 1 from pg_constraint where conrelid = 'public.intake_submissions'::regclass
                   and conname = 'intake_submissions_request_pair_check') then
        alter table public.intake_submissions add constraint intake_submissions_request_pair_check check (
            (request_id is null and request_fingerprint is null)
            or (request_id is not null and request_fingerprint is not null
                and request_fingerprint ~ '^[0-9a-f]{64}$')
        );
    end if;
    if not exists (select 1 from pg_constraint where conrelid = 'public.intake_submissions'::regclass
                   and conname = 'intake_submissions_match_outcome_check') then
        alter table public.intake_submissions add constraint intake_submissions_match_outcome_check check (
            customer_match_outcome in ('new_customer', 'reused_exact', 'selected_by_staff', 'needs_review')
        );
    end if;
end;
$$;

comment on column public.intake_submissions.request_id is
    'Caller-generated UUID per logical submission, retained across uncertain retries; NULL for legacy writes.';
comment on column public.intake_submissions.request_fingerprint is
    'SQL-computed SHA-256 of original request including trusted origin/actor/target/context. Immutable.';
comment on column public.intake_submissions.customer_match_outcome is
    'Immutable initial-creation matching outcome; NULL for legacy rows and follow-ups. Not a mutable review status.';

create or replace function public.protect_intake_submission()
returns trigger language plpgsql security invoker
set search_path = pg_catalog, pg_temp
as $$
begin
    if tg_op in ('DELETE', 'TRUNCATE') then
        raise exception 'Intake submissions must be preserved; use review status instead.' using errcode = '23514';
    end if;
    if row(new.id, new.booking_id, new.intake_link_id, new.submission_number,
           new.submitted_data, new.submitted_at, new.entry_method, new.submitted_by,
           new.request_id, new.request_fingerprint, new.customer_match_outcome)
       is distinct from
       row(old.id, old.booking_id, old.intake_link_id, old.submission_number,
           old.submitted_data, old.submitted_at, old.entry_method, old.submitted_by,
           old.request_id, old.request_fingerprint, old.customer_match_outcome) then
        raise exception 'Original intake answers and submission provenance cannot be changed.' using errcode = '23514';
    end if;
    return new;
end;
$$;
revoke all on function public.protect_intake_submission() from public, anon, authenticated, service_role;

-- Keep both Phase 5.1 triggers; fail rather than silently omit protection.
do $$
begin
    if (select count(*) from pg_trigger where tgrelid = 'public.intake_submissions'::regclass
        and tgname in ('protect_intake_submission', 'protect_intake_submission_truncate')
        and tgenabled = 'O') <> 2 then
        raise exception 'Install/verify the Phase 5.1 preservation triggers first.';
    end if;
end;
$$;
notify pgrst, 'reload schema';
commit;
