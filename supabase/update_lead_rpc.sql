-- Phase 5.1 note-separation revision: installed definition verified 2026-09-28.
-- Rental notes belong only to bookings; preserve customers.notes and entry_method.
-- Run this entire file in the Supabase SQL Editor for the Bench Rental project.
-- The function is SECURITY INVOKER, so existing RLS policies still apply.

create or replace function public.update_lead(
    p_booking_number text,
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
    p_internal_notes text
)
returns table (booking_number text)
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
    v_booking_id uuid;
    v_customer_id uuid;
    v_facebook_identity_id uuid;
    v_matching_facebook_identity_id uuid;
    v_email text := nullif(lower(btrim(p_email)), '');
    v_phone text := nullif(btrim(p_phone), '');
    v_phone_digits text := regexp_replace(coalesce(p_phone, ''), '[^0-9]', '', 'g');
    v_facebook_identity text := nullif(btrim(p_facebook_identity), '');
begin
    if auth.uid() is null then
        raise exception 'Authentication is required.';
    end if;
    if nullif(btrim(p_booking_number), '') is null then
        raise exception 'Booking number is required.';
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

    select b.id, b.primary_customer_id
    into v_booking_id, v_customer_id
    from public.bookings b
    where b.booking_number = p_booking_number
      and b.stage = 'lead'
    for update;

    if v_booking_id is null or v_customer_id is null then
        raise exception 'The selected lead is unavailable for editing.';
    end if;

    perform 1
    from public.customers c
    where c.id = v_customer_id and not c.is_archived
    for update;
    if not found then
        raise exception 'The selected customer is unavailable.';
    end if;

    if v_email is not null and exists (
        select 1 from public.customers c
        where c.id <> v_customer_id
          and not c.is_archived
          and lower(btrim(c.email)) = v_email
    ) then
        raise exception 'That email belongs to another customer.';
    end if;
    if v_phone is not null and exists (
        select 1 from public.customers c
        where c.id <> v_customer_id
          and not c.is_archived
          and regexp_replace(coalesce(c.phone, ''), '[^0-9]', '', 'g') = v_phone_digits
    ) then
        raise exception 'That phone belongs to another customer.';
    end if;
    if v_facebook_identity is not null and exists (
        select 1 from public.customer_identities ci
        where ci.customer_id <> v_customer_id
          and ci.identity_type = 'facebook'
          and lower(btrim(ci.display_value)) = lower(v_facebook_identity)
    ) then
        raise exception 'That Facebook identity belongs to another customer.';
    end if;

    select ci.id
    into v_facebook_identity_id
    from public.customer_identities ci
    where ci.customer_id = v_customer_id
      and ci.identity_type = 'facebook'
    order by ci.is_primary_for_type desc, ci.created_at, ci.id
    limit 1
    for update;

    if v_facebook_identity is not null then
        select ci.id
        into v_matching_facebook_identity_id
        from public.customer_identities ci
        where ci.customer_id = v_customer_id
          and ci.identity_type = 'facebook'
          and lower(btrim(ci.display_value)) = lower(v_facebook_identity)
        order by ci.is_primary_for_type desc, ci.created_at, ci.id
        limit 1
        for update;
    end if;

    if v_facebook_identity is null then
        if v_facebook_identity_id is not null then
            delete from public.customer_identities
            where id = v_facebook_identity_id;

            update public.customer_identities
            set is_primary_for_type = true,
                updated_at = now()
            where id = (
                select ci.id
                from public.customer_identities ci
                where ci.customer_id = v_customer_id
                  and ci.identity_type = 'facebook'
                order by ci.created_at, ci.id
                limit 1
            );
        end if;
    elsif v_matching_facebook_identity_id is not null then
        if v_facebook_identity_id is not null
           and v_facebook_identity_id <> v_matching_facebook_identity_id then
            delete from public.customer_identities
            where id = v_facebook_identity_id;
        end if;

        update public.customer_identities
        set is_primary_for_type = (id = v_matching_facebook_identity_id),
            updated_at = now()
        where customer_id = v_customer_id
          and identity_type = 'facebook';

        update public.customer_identities
        set display_value = v_facebook_identity
        where id = v_matching_facebook_identity_id;
    else
        update public.customer_identities
        set is_primary_for_type = false,
            updated_at = now()
        where customer_id = v_customer_id
          and identity_type = 'facebook'
          and id is distinct from v_facebook_identity_id;

        if v_facebook_identity_id is null then
            insert into public.customer_identities (
                customer_id, identity_type, display_value, is_primary_for_type
            ) values (
                v_customer_id, 'facebook', v_facebook_identity, true
            );
        else
            update public.customer_identities
            set display_value = v_facebook_identity,
                is_primary_for_type = true,
                updated_at = now()
            where id = v_facebook_identity_id;
        end if;
    end if;

    if p_preferred_contact_method = 'email' and v_email is null
       or p_preferred_contact_method in ('text', 'phone') and v_phone is null
       or p_preferred_contact_method = 'facebook' and not exists (
            select 1 from public.customer_identities ci
            where ci.customer_id = v_customer_id
              and ci.identity_type = 'facebook'
       ) then
        raise exception 'Preferred contact information is missing.';
    end if;

    update public.customers
    set preferred_name = btrim(p_customer_name),
        email = v_email,
        phone = v_phone,
        preferred_contact_method = p_preferred_contact_method,
        updated_at = now()
    where id = v_customer_id;

    update public.bookings
    set source = p_source,
        event_type = nullif(btrim(p_event_type), ''),
        event_date = p_event_date,
        requested_bench_count = p_requested_bench_count,
        facebook_conversation_url = nullif(btrim(p_facebook_conversation_url), ''),
        customer_notes = nullif(btrim(p_customer_notes), ''),
        internal_notes = nullif(btrim(p_internal_notes), ''),
        updated_at = now()
    where id = v_booking_id;

    return query select p_booking_number;
end;
$$;

revoke all on function public.update_lead(
    text, text, date, integer, text, text, text, text, text,
    text, text, text, text
) from public, anon;

grant execute on function public.update_lead(
    text, text, date, integer, text, text, text, text, text,
    text, text, text, text
) to authenticated;

-- Safe installation check (returns one row when the function exists):
select p.proname as function_name
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname = 'update_lead';
