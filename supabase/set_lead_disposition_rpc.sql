-- Run this entire file in the Supabase SQL Editor for the Bench Rental project.
-- The function is SECURITY INVOKER, so existing RLS policies still apply.

create or replace function public.set_lead_disposition(
    p_booking_number text,
    p_target_stage text,
    p_reason text
)
returns table (booking_number text, stage text)
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
    v_booking_id uuid;
    v_current_stage text;
    v_reason text := nullif(btrim(p_reason), '');
begin
    if auth.uid() is null then
        raise exception 'Authentication is required.';
    end if;
    if nullif(btrim(p_booking_number), '') is null then
        raise exception 'Booking number is required.';
    end if;
    if p_target_stage is null
       or p_target_stage not in ('lead', 'lost', 'cancelled') then
        raise exception 'Invalid lead status.';
    end if;

    select b.id, b.stage
    into v_booking_id, v_current_stage
    from public.bookings b
    where b.booking_number = btrim(p_booking_number)
    for update;

    if not found then
        raise exception 'The selected booking was not found.';
    end if;

    if p_target_stage in ('lost', 'cancelled') then
        if v_current_stage <> 'lead' then
            raise exception 'Only an active lead can be closed.';
        end if;
        if v_reason is null then
            raise exception 'A closure reason is required.';
        end if;
    elsif v_current_stage not in ('lost', 'cancelled') then
        raise exception 'Only a lost or cancelled lead can be restored.';
    end if;

    update public.bookings
    set stage = p_target_stage,
        lost_reason = case
            when p_target_stage = 'lost' then v_reason
            else null
        end,
        cancellation_reason = case
            when p_target_stage = 'cancelled' then v_reason
            else null
        end,
        updated_at = now()
    where id = v_booking_id;

    return query
    select b.booking_number, b.stage
    from public.bookings b
    where b.id = v_booking_id;
end;
$$;

revoke all on function public.set_lead_disposition(text, text, text)
from public, anon;

grant execute on function public.set_lead_disposition(text, text, text)
to authenticated;

-- Safe installation check (returns one row when the function exists):
select p.proname as function_name
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname = 'set_lead_disposition';
