-- Requires inquiry_model.sql first. Installed definition verified 2026-09-28.
-- Rental notes belong only to bookings; preserve customers.notes.
-- Run this entire file in the Supabase SQL Editor for the Bench Rental project.
-- The function is SECURITY INVOKER, so existing RLS policies still apply.

create or replace function public.create_lead(
    p_customer_name text,
    p_event_date date,
    p_requested_bench_count integer,
    p_preferred_contact_method text,
    p_source text,
    p_email text,
    p_phone text,
    p_facebook_identity text,
    p_event_type text,
    p_facebook_conversation_url text,
    p_customer_notes text,
    p_internal_notes text,
    p_existing_customer_id uuid
)
returns table (booking_id uuid, booking_number text)
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
    v_customer_id uuid;
    v_booking_id uuid;
    v_booking_number text;
    v_email text := nullif(lower(btrim(p_email)), '');
    v_phone text := nullif(btrim(p_phone), '');
    v_phone_digits text := regexp_replace(coalesce(p_phone, ''), '[^0-9]', '', 'g');
    v_facebook_identity text := nullif(btrim(p_facebook_identity), '');
    v_event_year integer;
    v_next_sequence integer;
begin
    if auth.uid() is null then
        raise exception 'Authentication is required.';
    end if;
    if nullif(btrim(p_customer_name), '') is null then
        raise exception 'Customer name is required.';
    end if;
    if p_event_date is null then
        raise exception 'Event date is required.';
    end if;
    if p_requested_bench_count is null or p_requested_bench_count < 1 then
        raise exception 'Requested bench count must be positive.';
    end if;
    if p_source not in (
        'facebook_marketplace', 'facebook_referral', 'word_of_mouth',
        'repeat_customer', 'other'
    ) then
        raise exception 'Invalid lead source.';
    end if;
    if p_preferred_contact_method not in ('facebook', 'text', 'phone', 'email') then
        raise exception 'Invalid preferred contact method.';
    end if;
    if v_email is null and v_phone is null and v_facebook_identity is null then
        raise exception 'At least one contact method is required.';
    end if;
    if v_email is not null and v_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' then
        raise exception 'Invalid email address.';
    end if;
    if v_phone is not null and length(v_phone_digits) not between 7 and 15 then
        raise exception 'Invalid phone number.';
    end if;
    if p_preferred_contact_method = 'email' and v_email is null
       or p_preferred_contact_method in ('text', 'phone') and v_phone is null
       or p_preferred_contact_method = 'facebook' and v_facebook_identity is null then
        raise exception 'Preferred contact information is missing.';
    end if;

    if p_existing_customer_id is null then
        insert into public.customers (
            preferred_name, email, phone, preferred_contact_method
        ) values (
            btrim(p_customer_name), v_email, v_phone,
            p_preferred_contact_method
        )
        returning id into v_customer_id;
    else
        update public.customers
        set preferred_name = btrim(p_customer_name),
            email = coalesce(v_email, email),
            phone = coalesce(v_phone, phone),
            preferred_contact_method = p_preferred_contact_method,
            updated_at = now()
        where id = p_existing_customer_id and not is_archived
        returning id into v_customer_id;

        if v_customer_id is null then
            raise exception 'The selected customer is unavailable.';
        end if;
    end if;

    if v_facebook_identity is not null and not exists (
        select 1
        from public.customer_identities ci
        where ci.customer_id = v_customer_id
          and ci.identity_type = 'facebook'
          and lower(btrim(ci.display_value)) = lower(v_facebook_identity)
    ) then
        insert into public.customer_identities (
            customer_id, identity_type, display_value, is_primary_for_type
        ) values (
            v_customer_id, 'facebook', v_facebook_identity,
            not exists (
                select 1 from public.customer_identities ci
                where ci.customer_id = v_customer_id
                  and ci.identity_type = 'facebook'
            )
        );
    end if;

    v_event_year := extract(year from p_event_date)::integer;
    perform pg_advisory_xact_lock(hashtextextended('booking-number-' || v_event_year, 0));

    select coalesce(max((regexp_match(b.booking_number, '-([0-9]+)$'))[1]::integer), 0) + 1
    into v_next_sequence
    from public.bookings b
    where b.booking_number ~ ('^BR-' || v_event_year || '-[0-9]+$');

    v_booking_number := 'BR-' || v_event_year || '-' || lpad(v_next_sequence::text, 3, '0');

    insert into public.bookings (
        booking_number, primary_customer_id, stage, source, event_type,
        event_date, requested_bench_count, facebook_conversation_url,
        customer_notes, internal_notes, created_by, entry_method
    ) values (
        v_booking_number, v_customer_id, 'lead', p_source,
        nullif(btrim(p_event_type), ''), p_event_date,
        p_requested_bench_count, nullif(btrim(p_facebook_conversation_url), ''),
        nullif(btrim(p_customer_notes), ''), nullif(btrim(p_internal_notes), ''),
        auth.uid(), 'staff_entered'
    )
    returning id into v_booking_id;

    insert into public.booking_contacts (
        booking_id, customer_id, contact_role, is_primary
    ) values (
        v_booking_id, v_customer_id, 'primary_customer', true
    );

    return query select v_booking_id, v_booking_number;
end;
$$;

revoke all on function public.create_lead(
    text, date, integer, text, text, text, text, text,
    text, text, text, text, uuid
) from public, anon;

grant execute on function public.create_lead(
    text, date, integer, text, text, text, text, text,
    text, text, text, text, uuid
) to authenticated;

-- Safe installation check (returns one row when the function exists):
select p.proname as function_name
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname = 'create_lead';
