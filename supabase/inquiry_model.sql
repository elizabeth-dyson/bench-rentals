-- Phase 5.1: user installed; post-installation metadata/definitions verified 2026-09-28.
-- Behavioral database integration tests remain unrun.
-- First run inspect_inquiry_schema.sql and compare with docs/DATABASE.md.
-- Install this file, then create_lead_rpc.sql, then update_lead_rpc.sql.
-- No existing answers, notes, origins, addresses, or booking identifiers are rewritten.
begin;

alter table public.bookings
    add column if not exists entry_method text,
    add column if not exists timing_notes text;
alter table public.intake_submissions
    add column if not exists entry_method text,
    add column if not exists submitted_by uuid;

do $$
begin
    if not exists (select 1 from pg_constraint where conrelid = 'public.bookings'::regclass
                   and conname = 'bookings_entry_method_check') then
        alter table public.bookings add constraint bookings_entry_method_check
            check (entry_method in ('public_form', 'staff_entered'));
    end if;
    if not exists (select 1 from pg_constraint where conrelid = 'public.intake_submissions'::regclass
                   and conname = 'intake_submissions_entry_method_check') then
        alter table public.intake_submissions add constraint intake_submissions_entry_method_check
            check (entry_method in ('public_form', 'staff_entered'));
    end if;
    if not exists (select 1 from pg_constraint where conrelid = 'public.intake_submissions'::regclass
                   and conname = 'intake_submissions_attribution_check') then
        alter table public.intake_submissions add constraint intake_submissions_attribution_check
            check (
                (entry_method is null and submitted_by is null)
                or (entry_method is not null and entry_method = 'public_form' and submitted_by is null)
                or (entry_method is not null and entry_method = 'staff_entered' and submitted_by is not null)
            );
    end if;
end;
$$;

alter table public.venues
    alter column address_line_1 drop not null,
    alter column city drop not null,
    alter column state drop not null,
    alter column state drop default,
    alter column postal_code drop not null;

comment on column public.bookings.entry_method is
    'Initial entry origin: public_form or staff_entered; NULL means legacy/unknown. Independent of referral source.';
comment on column public.bookings.timing_notes is
    'Working timing requests; not an inventory window or confirmed appointment.';
comment on column public.intake_submissions.entry_method is
    'Origin of this submission; NULL means legacy/unknown.';
comment on column public.intake_submissions.submitted_by is
    'Authenticated staff UUID for staff_entered submissions; NULL for public or legacy submissions.';
comment on column public.customers.notes is 'Customer-wide staff context; not rental-specific notes.';
comment on column public.bookings.customer_notes is 'Rental-specific notes or customer requests.';
comment on column public.bookings.internal_notes is 'Staff-only context for this rental.';

create or replace function public.protect_intake_submission()
returns trigger
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
begin
    if tg_op in ('DELETE', 'TRUNCATE') then
        raise exception 'Intake submissions must be preserved; use review status instead.'
            using errcode = '23514';
    end if;
    if row(new.id, new.booking_id, new.intake_link_id, new.submission_number,
           new.submitted_data, new.submitted_at, new.entry_method, new.submitted_by)
       is distinct from
       row(old.id, old.booking_id, old.intake_link_id, old.submission_number,
           old.submitted_data, old.submitted_at, old.entry_method, old.submitted_by) then
        raise exception 'Original intake answers and submission provenance cannot be changed.'
            using errcode = '23514';
    end if;
    return new;
end;
$$;

revoke all on function public.protect_intake_submission() from public, anon, authenticated;
drop trigger if exists protect_intake_submission on public.intake_submissions;
create trigger protect_intake_submission
before update or delete on public.intake_submissions
for each row execute function public.protect_intake_submission();
drop trigger if exists protect_intake_submission_truncate on public.intake_submissions;
create trigger protect_intake_submission_truncate
before truncate on public.intake_submissions
for each statement execute function public.protect_intake_submission();

-- RLS policies and table grants are deliberately unchanged.
notify pgrst, 'reload schema';
commit;

-- Metadata verification (no business rows).
select table_name, column_name, is_nullable, column_default
from information_schema.columns
where table_schema = 'public' and (
    (table_name = 'bookings' and column_name in ('entry_method', 'timing_notes'))
    or (table_name = 'intake_submissions' and column_name in ('entry_method', 'submitted_by', 'booking_id'))
    or (table_name = 'venues' and column_name in ('address_line_1', 'city', 'state', 'postal_code'))
)
order by table_name, column_name;
