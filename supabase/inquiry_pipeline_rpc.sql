-- Phase 5.3 INSTALL 2/2. Pending user installation and database verification.
-- Requires inquiry_pipeline_schema.sql. No public/anonymous endpoint is enabled.
-- Install as the trusted database owner. Never grant application roles access
-- to inquiry_private. Wrappers are the sole authenticated entry points.
begin;

create or replace function inquiry_private.clean_text(p_value text)
returns text language sql immutable security invoker
set search_path = pg_catalog, pg_temp
as $$ select nullif(regexp_replace(p_value, '^[[:space:]]+|[[:space:]]+$', '', 'g'), '') $$;

create or replace function inquiry_private.contact_value(p_kind text, p_value text)
returns text language sql immutable security invoker
set search_path = pg_catalog, pg_temp
as $$
    select case p_kind
        when 'email' then lower(inquiry_private.clean_text(p_value))
        when 'phone' then nullif(regexp_replace(p_value, '[^0-9]', '', 'g'), '')
        when 'facebook' then lower(regexp_replace(inquiry_private.clean_text(p_value), '[[:space:]]+', ' ', 'g'))
    end
$$;

-- Validate the full v1 wire contract, then derive normalized working answers.
-- All timestamps have explicit ISO offsets; no session timezone parsing defaults.
create or replace function inquiry_private.normalize_snapshot(p_snapshot jsonb)
returns jsonb language plpgsql security invoker
set search_path = pg_catalog, pg_temp
set timezone = 'America/Chicago'
set datestyle = 'ISO, YMD'
as $$
declare
    v_answers jsonb;
    v_work jsonb;
    v_venue jsonb := '{}'::jsonb;
    v_field text;
    v_value text;
    v_time timestamptz;
    v_fields constant text[] := array[
        'customer_name','event_date','requested_bench_count','preferred_contact_method',
        'email','phone','facebook_identity','event_type','source','venue','delivery_preference',
        'delivery_at','setup_complete_by','event_start_at','pickup_at','rehearsal_at',
        'timing_notes','rental_notes','delivery_instructions','pickup_instructions'];
    v_venue_fields constant text[] := array['name','address_line_1','address_line_2','city','state','postal_code'];
begin
    if jsonb_typeof(p_snapshot) is distinct from 'object'
       or p_snapshot->'schema_version' is distinct from '1'::jsonb
       or not (p_snapshot ?& array['schema_version','answers'])
       or (p_snapshot - array['schema_version','answers']) <> '{}'::jsonb
       or jsonb_typeof(p_snapshot->'answers') is distinct from 'object' then
        raise exception 'Invalid snapshot envelope.' using errcode = 'P5101';
    end if;
    v_answers := p_snapshot->'answers';
    if not (v_answers ?& v_fields) or (v_answers - v_fields) <> '{}'::jsonb then
        raise exception 'Supply exactly the complete v1 answer fields.' using errcode = 'P5101';
    end if;
    v_work := v_answers;
    foreach v_field in array v_fields loop
        if v_field in ('venue','requested_bench_count') then continue; end if;
        if jsonb_typeof(v_answers->v_field) not in ('string','null') then
            raise exception 'Answer fields must be text or null.' using errcode = 'P5101';
        end if;
        v_work := jsonb_set(v_work, array[v_field], coalesce(to_jsonb(inquiry_private.clean_text(v_answers->>v_field)), 'null'::jsonb));
    end loop;
    if v_work->>'customer_name' is null
       or coalesce(v_answers->>'preferred_contact_method','') not in ('email','phone','text','facebook')
       or coalesce(v_answers->>'delivery_preference','') not in ('parent_delivery','customer_pickup','unsure') then
        raise exception 'Required answers are missing or invalid.' using errcode = 'P5101';
    end if;
    if jsonb_typeof(v_answers->'requested_bench_count') is distinct from 'number'
       or (v_answers->>'requested_bench_count') !~ '^[1-9][0-9]*$'
       or (v_answers->>'requested_bench_count')::numeric > 2147483647 then
        raise exception 'Bench count must be a positive database integer.' using errcode = 'P5101';
    end if;
    v_value := v_answers->>'event_date';
    if v_value is null or v_value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
       or v_value::date < date '0001-01-01' then
        raise exception 'Invalid event date.' using errcode = 'P5101';
    end if;
    foreach v_field in array array['email','phone','facebook_identity'] loop
        v_value := inquiry_private.contact_value(case when v_field = 'facebook_identity' then 'facebook' else v_field end, v_answers->>v_field);
        v_work := jsonb_set(v_work, array[v_field], coalesce(to_jsonb(v_value), 'null'::jsonb));
    end loop;
    if v_work->>'email' is not null and (v_work->>'email') !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' then
        raise exception 'Invalid email.' using errcode = 'P5101';
    end if;
    if inquiry_private.clean_text(v_answers->>'phone') is not null
       and (v_work->>'phone' is null or length(v_work->>'phone') not between 7 and 15) then
        raise exception 'Invalid phone.' using errcode = 'P5101';
    end if;
    if coalesce(v_work->>'email',v_work->>'phone',v_work->>'facebook_identity') is null
       or (v_work->>'preferred_contact_method' = 'email' and v_work->>'email' is null)
       or (v_work->>'preferred_contact_method' in ('phone','text') and v_work->>'phone' is null)
       or (v_work->>'preferred_contact_method' = 'facebook' and v_work->>'facebook_identity' is null) then
        raise exception 'Preferred contact information is required.' using errcode = 'P5101';
    end if;
    v_value := coalesce(v_work->>'source','other');
    if v_value not in ('facebook_marketplace','facebook_referral','word_of_mouth','repeat_customer','other') then
        raise exception 'Invalid referral source.' using errcode = 'P5101';
    end if;
    v_work := jsonb_set(v_work, '{source}', to_jsonb(v_value));
    if v_answers->'venue' <> 'null'::jsonb then
        if jsonb_typeof(v_answers->'venue') is distinct from 'object'
           or not (v_answers->'venue' ?& v_venue_fields)
           or ((v_answers->'venue') - v_venue_fields) <> '{}'::jsonb then
            raise exception 'Invalid venue fields.' using errcode = 'P5101';
        end if;
        foreach v_field in array v_venue_fields loop
            if jsonb_typeof(v_answers->'venue'->v_field) not in ('string','null') then
                raise exception 'Venue fields must be text or null.' using errcode = 'P5101';
            end if;
            v_venue := v_venue || jsonb_build_object(v_field, inquiry_private.clean_text(v_answers->'venue'->>v_field));
        end loop;
    end if;
    v_work := jsonb_set(v_work, '{venue}', case when jsonb_strip_nulls(v_venue) = '{}'::jsonb then 'null'::jsonb else v_venue end);
    foreach v_field in array array['delivery_at','setup_complete_by','event_start_at','pickup_at','rehearsal_at'] loop
        v_value := v_answers->>v_field;
        if v_value is null then continue; end if;
        if v_value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$'
           or substring(v_value,12,2)::integer > 23
           or substring(v_value,15,2)::integer > 59
           or substring(v_value,18,2)::integer > 59 then
            raise exception 'Timestamps require valid ISO times with explicit offsets.' using errcode = 'P5101';
        end if;
        -- PostgreSQL rejects impossible dates/offsets; original offset text stays in the snapshot.
        v_time := v_value::timestamptz;
        if not isfinite(v_time) then
            raise exception 'Invalid timestamp.' using errcode = 'P5101';
        end if;
        v_work := jsonb_set(v_work, array[v_field], to_jsonb(v_time));
    end loop;
    if (v_work->>'pickup_at')::timestamptz < (v_work->>'delivery_at')::timestamptz then
        raise exception 'Pickup precedes delivery.' using errcode = 'P5101';
    end if;
    return v_work;
exception when data_exception then
    raise exception 'Invalid inquiry value.' using errcode = 'P5101';
end;
$$;

-- PRIVATE trusted operation. p_booking_id is resolved by the authorized wrapper,
-- never by a public caller. Future private-link authorization belongs in 5.4.
create or replace function inquiry_private.submit_inquiry(
    p_request_id uuid, p_snapshot jsonb, p_origin text, p_actor uuid,
    p_booking_id uuid default null, p_staff_context jsonb default '{}'::jsonb
)
returns table(booking_id uuid, booking_number text, submission_id uuid, submission_number integer, replayed boolean)
language plpgsql security invoker
set search_path = pg_catalog, pg_temp
set timezone = 'America/Chicago'
as $$
declare
    v_work jsonb;
    v_context jsonb;
    v_fingerprint text;
    v_previous public.intake_submissions%rowtype;
    v_booking public.bookings%rowtype;
    v_customer uuid;
    v_venue uuid;
    v_submission uuid;
    v_submission_number integer;
    v_match text;
    v_kind text;
    v_value text;
    v_contact jsonb;
    v_candidates uuid[];
    v_exact uuid;
    v_consistent boolean := true;
    v_has_match boolean := false;
    v_year integer;
    v_sequence integer;
begin
    if p_request_id is null then raise exception 'Request ID is required.' using errcode = 'P5101'; end if;
    if p_origin is null or p_origin not in ('staff_entered','public_form')
       or (p_origin = 'staff_entered' and p_actor is null)
       or (p_origin = 'public_form' and p_actor is not null) then
        raise exception 'Invalid trusted provenance.' using errcode = '42501';
    end if;
    if jsonb_typeof(p_staff_context) is distinct from 'object'
       or (p_staff_context - array['existing_customer_id','internal_notes','facebook_conversation_url']) <> '{}'::jsonb then
        raise exception 'Invalid staff context.' using errcode = 'P5101';
    end if;
    -- Canonicalize omitted optional context keys; keep original accepted text.
    v_context := jsonb_build_object('existing_customer_id', p_staff_context->'existing_customer_id',
        'internal_notes', p_staff_context->'internal_notes', 'facebook_conversation_url', p_staff_context->'facebook_conversation_url');
    for v_kind in select jsonb_object_keys(v_context) loop
        if jsonb_typeof(v_context->v_kind) not in ('string','null') then
            raise exception 'Invalid staff context value.' using errcode = 'P5101';
        end if;
    end loop;
    if (p_origin = 'public_form' or p_booking_id is not null)
       and jsonb_strip_nulls(v_context) <> '{}'::jsonb then
        raise exception 'Staff context is not accepted for this operation.' using errcode = 'P5101';
    end if;
    v_fingerprint := encode(sha256(convert_to(jsonb_build_object(
        'snapshot', p_snapshot, 'operation', case when p_booking_id is null then 'create' else 'append' end,
        'booking_id', p_booking_id, 'origin', p_origin, 'actor', p_actor, 'context', v_context
    )::text, 'UTF8')), 'hex');
    perform pg_advisory_xact_lock(hashtextextended('inquiry-request-' || p_request_id, 0));
    select s.* into v_previous from public.intake_submissions s where s.request_id = p_request_id;
    if found then
        if v_previous.request_fingerprint is distinct from v_fingerprint then
            raise exception 'Request conflicts with an earlier submission.' using errcode = 'P5104';
        end if;
        select b.* into strict v_booking from public.bookings b where b.id = v_previous.booking_id;
        return query select v_booking.id, v_booking.booking_number, v_previous.id, v_previous.submission_number, true;
        return;
    end if;
    v_work := inquiry_private.normalize_snapshot(p_snapshot);
    if p_booking_id is not null then
        select b.* into v_booking from public.bookings b where b.id = p_booking_id for update;
        if not found then raise exception 'Booking unavailable.' using errcode = 'P5102'; end if;
        if v_booking.stage <> 'lead' then raise exception 'Booking is not an open lead.' using errcode = 'P5103'; end if;
        select coalesce(max(s.submission_number), 0) + 1 into v_submission_number
        from public.intake_submissions s where s.booking_id = p_booking_id;
    else
        v_contact := jsonb_strip_nulls(jsonb_build_object(
            'email', v_work->'email', 'phone', v_work->'phone', 'facebook', v_work->'facebook_identity'));
        -- Same ordered contact locks for automatic and explicit selection. At the
        -- default READ COMMITTED isolation, queries after waiting see committed matches.
        for v_kind, v_value in select key, value from jsonb_each_text(v_contact) order by key, value loop
            perform pg_advisory_xact_lock(hashtextextended('inquiry-contact-' || v_kind || ':' || v_value, 0));
        end loop;
        begin
            v_customer := (v_context->>'existing_customer_id')::uuid;
        exception when invalid_text_representation then
            raise exception 'Invalid customer ID.' using errcode = 'P5101';
        end;
        if v_customer is not null then
            perform 1 from public.customers c where c.id = v_customer and not c.is_archived for update;
            if not found then raise exception 'Customer unavailable.' using errcode = 'P5102'; end if;
            v_match := 'selected_by_staff';
        else
            for v_kind, v_value in select key, value from jsonb_each_text(v_contact) order by key loop
                select coalesce(array_agg(distinct c.id order by c.id), '{}'::uuid[]) into v_candidates
                from public.customers c where not c.is_archived and (
                    (v_kind = 'email' and inquiry_private.contact_value('email', c.email) = v_value)
                    or (v_kind = 'phone' and inquiry_private.contact_value('phone', c.phone) = v_value)
                    or (v_kind = 'facebook' and exists (select 1 from public.customer_identities ci
                        where ci.customer_id = c.id and ci.identity_type = 'facebook'
                        and inquiry_private.contact_value('facebook', ci.display_value) = v_value))
                );
                if cardinality(v_candidates) > 0 then v_has_match := true; end if;
                if cardinality(v_candidates) <> 1 then v_consistent := false;
                elsif v_exact is null then v_exact := v_candidates[1];
                elsif v_exact <> v_candidates[1] then v_consistent := false;
                end if;
            end loop;
            if v_consistent and v_exact is not null then
                -- Lock and revalidate against concurrent profile edits/archival.
                select c.id into v_customer from public.customers c
                where c.id = v_exact and not c.is_archived
                  and (v_work->>'email' is null or inquiry_private.contact_value('email',c.email) = v_work->>'email')
                  and (v_work->>'phone' is null or inquiry_private.contact_value('phone',c.phone) = v_work->>'phone')
                  and (v_work->>'facebook_identity' is null or exists (select 1 from public.customer_identities ci
                      where ci.customer_id = c.id and ci.identity_type = 'facebook'
                      and inquiry_private.contact_value('facebook',ci.display_value) = v_work->>'facebook_identity'))
                for update;
                if found then v_match := 'reused_exact'; end if;
            end if;
            if v_customer is null then
                v_match := case when v_has_match then 'needs_review' else 'new_customer' end;
                insert into public.customers(preferred_name,email,phone,preferred_contact_method)
                values(v_work->>'customer_name',v_work->>'email',v_work->>'phone',v_work->>'preferred_contact_method')
                returning id into v_customer;
                if v_work->>'facebook_identity' is not null then
                    insert into public.customer_identities(customer_id,identity_type,display_value,is_primary_for_type)
                    values(v_customer,'facebook',v_work->>'facebook_identity',true);
                end if;
            end if;
        end if;
        if v_work->'venue' <> 'null'::jsonb then
            insert into public.venues(name,address_line_1,address_line_2,city,state,postal_code)
            values(v_work->'venue'->>'name',v_work->'venue'->>'address_line_1',v_work->'venue'->>'address_line_2',
                v_work->'venue'->>'city',v_work->'venue'->>'state',v_work->'venue'->>'postal_code') returning id into v_venue;
        end if;
        v_year := extract(year from (v_work->>'event_date')::date)::integer;
        perform pg_advisory_xact_lock(hashtextextended('booking-number-' || v_year, 0));
        select coalesce(max((regexp_match(b.booking_number, '-([0-9]+)$'))[1]::integer),0) + 1 into v_sequence
        from public.bookings b where b.booking_number ~ ('^BR-' || v_year || '-[0-9]+$');
        insert into public.bookings(booking_number,primary_customer_id,venue_id,stage,source,event_type,event_date,
            requested_bench_count,entry_method,created_by,delivery_method,delivery_at,setup_complete_by,
            event_start_at,pickup_at,rehearsal_at,timing_notes,customer_notes,internal_notes,
            delivery_instructions,pickup_instructions,facebook_conversation_url)
        values('BR-' || v_year || '-' || lpad(v_sequence::text,greatest(3,length(v_sequence::text)),'0'),
            v_customer,v_venue,'lead',v_work->>'source',v_work->>'event_type',(v_work->>'event_date')::date,
            (v_work->>'requested_bench_count')::integer,p_origin,p_actor,nullif(v_work->>'delivery_preference','unsure'),
            (v_work->>'delivery_at')::timestamptz,(v_work->>'setup_complete_by')::timestamptz,
            (v_work->>'event_start_at')::timestamptz,(v_work->>'pickup_at')::timestamptz,(v_work->>'rehearsal_at')::timestamptz,
            v_work->>'timing_notes',v_work->>'rental_notes',inquiry_private.clean_text(v_context->>'internal_notes'),
            v_work->>'delivery_instructions',v_work->>'pickup_instructions',inquiry_private.clean_text(v_context->>'facebook_conversation_url'))
        returning * into v_booking;
        insert into public.booking_contacts(booking_id,customer_id,contact_role,is_primary)
        values(v_booking.id,v_customer,'primary_customer',true);
        v_submission_number := 1;
    end if;
    insert into public.intake_submissions(booking_id,submission_number,submitted_data,review_status,
        entry_method,submitted_by,request_id,request_fingerprint,customer_match_outcome)
    values(v_booking.id,v_submission_number,p_snapshot,'pending',p_origin,p_actor,p_request_id,v_fingerprint,v_match)
    returning id into v_submission;
    return query select v_booking.id,v_booking.booking_number,v_submission,v_submission_number,false;
end;
$$;

create or replace function public.create_staff_inquiry(p_request_id uuid, p_snapshot jsonb, p_staff_context jsonb default '{}'::jsonb)
returns table(booking_id uuid, booking_number text, submission_id uuid, submission_number integer, replayed boolean)
language plpgsql security definer
set search_path = pg_catalog, pg_temp
as $$
begin
    if auth.uid() is null then raise exception 'Authentication required.' using errcode = '42501'; end if;
    return query select * from inquiry_private.submit_inquiry(p_request_id,p_snapshot,'staff_entered',auth.uid(),null,p_staff_context);
end;
$$;

create or replace function public.append_staff_inquiry_submission(p_request_id uuid, p_booking_id uuid, p_snapshot jsonb)
returns table(booking_id uuid, booking_number text, submission_id uuid, submission_number integer, replayed boolean)
language plpgsql security definer
set search_path = pg_catalog, pg_temp
as $$
begin
    if auth.uid() is null then raise exception 'Authentication required.' using errcode = '42501'; end if;
    if p_booking_id is null then raise exception 'Booking ID required.' using errcode = 'P5101'; end if;
    return query select * from inquiry_private.submit_inquiry(p_request_id,p_snapshot,'staff_entered',auth.uid(),p_booking_id,'{}'::jsonb);
end;
$$;

revoke all on all functions in schema inquiry_private from public, anon, authenticated, service_role;
revoke all on function public.create_staff_inquiry(uuid,jsonb,jsonb) from public, anon, authenticated, service_role;
revoke all on function public.append_staff_inquiry_submission(uuid,uuid,jsonb) from public, anon, authenticated, service_role;
grant execute on function public.create_staff_inquiry(uuid,jsonb,jsonb) to authenticated;
grant execute on function public.append_staff_inquiry_submission(uuid,uuid,jsonb) to authenticated;
notify pgrst, 'reload schema';
commit;
