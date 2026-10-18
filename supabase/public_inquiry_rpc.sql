-- Phase 5.4 INSTALL 2/2. Requires public_inquiry_schema.sql; owner installation.
-- PENDING manual installation and isolated behavioral/concurrency verification.
begin;
create or replace function public.create_public_inquiry(
    p_request_id uuid, p_snapshot jsonb, p_gateway_secret text, p_session_id uuid
)
returns table(accepted boolean, request_id uuid, replayed boolean)
language plpgsql security definer
set search_path = pg_catalog, pg_temp
set timezone = 'UTC'
as $$
declare
    v_config inquiry_private.public_config%rowtype;
    v_result record;
    v_field text;
    v_limit integer;
    v_now timestamptz;
    v_start timestamptz;
    v_duration interval;
    v_key text;
    v_used integer;
    v_index integer;
begin
    -- Secret checks always precede replay and any inquiry lookup/validation.
    select * into v_config from inquiry_private.public_config where singleton;
    if not found or not v_config.enabled or v_config.gateway_secret_hash is null
        or p_gateway_secret is null or length(p_gateway_secret) not between 43 and 128
        or encode(sha256(convert_to(p_gateway_secret,'UTF8')),'hex') <> v_config.gateway_secret_hash then
        raise exception 'Public submission unavailable.' using errcode='42501';
    end if;
    if p_request_id is null or p_session_id is null then
        raise exception 'Invalid request.' using errcode='P5101';
    end if;
    if p_snapshot is null or octet_length(p_snapshot::text) > 65536 then
        raise exception 'Invalid inquiry size.' using errcode='P5101';
    end if;
    for v_field, v_limit in select * from (values
        ('customer_name',200),('event_type',200),('email',254),('phone',50),
        ('facebook_identity',500),('timing_notes',4000),('rental_notes',4000),
        ('delivery_instructions',4000),('pickup_instructions',4000)
    ) as limits(field_name,max_length) loop
        if length(p_snapshot->'answers'->>v_field) > v_limit then
            raise exception 'Inquiry field too long.' using errcode='P5101';
        end if;
    end loop;
    if jsonb_typeof(p_snapshot->'answers'->'venue') = 'object' then
        if exists(select 1 from jsonb_each_text(p_snapshot->'answers'->'venue') v where length(v.value)>200) then
            raise exception 'Venue field too long.' using errcode='P5101';
        end if;
    end if;

    -- Same lock as 5.3: simultaneous identical requests see one committed result.
    perform pg_advisory_xact_lock(hashtextextended('inquiry-request-' || p_request_id,0));
    -- Serialize all budget changes and recheck configuration after waiting.
    select * into strict v_config from inquiry_private.public_config where singleton for update;
    if not v_config.enabled or v_config.gateway_secret_hash is null
       or encode(sha256(convert_to(p_gateway_secret,'UTF8')),'hex') <> v_config.gateway_secret_hash then
        raise exception 'Public submission unavailable.' using errcode='42501';
    end if;
    if exists(select 1 from public.intake_submissions s where s.request_id=p_request_id) then
        -- The shared operation checks exact fingerprint, operation, and provenance.
        select * into strict v_result from inquiry_private.submit_inquiry(
            p_request_id,p_snapshot,'public_form',null,null,'{}'::jsonb);
        return query select true,p_request_id,v_result.replayed;
        return;
    end if;

    -- Reject invalid snapshots before allocating budget. The shared operation also validates.
    perform inquiry_private.normalize_snapshot(p_snapshot);
    v_now := clock_timestamp();
    delete from inquiry_private.public_rate_buckets where expires_at <= v_now;
    for v_index in 1..3 loop
        if v_index=1 then
            v_key := 'session:' || encode(sha256(convert_to(p_session_id::text,'UTF8')),'hex');
            v_start := date_bin(interval '15 minutes',v_now,'2000-01-01 00:00:00+00'::timestamptz);
            v_duration := interval '15 minutes'; v_limit := v_config.session_limit;
        elsif v_index=2 then
            v_key := 'global:hour'; v_start := date_trunc('hour',v_now);
            v_duration := interval '1 hour'; v_limit := v_config.hourly_limit;
        else
            v_key := 'global:day'; v_start := date_trunc('day',v_now);
            v_duration := interval '1 day'; v_limit := v_config.daily_limit;
        end if;
        select b.used into v_used from inquiry_private.public_rate_buckets b
            where b.bucket_key=v_key and b.starts_at=v_start;
        if coalesce(v_used,0) >= v_limit then
            raise exception 'Submission limit reached.' using errcode='P5401';
        end if;
        insert into inquiry_private.public_rate_buckets(bucket_key,starts_at,expires_at,used)
            values(v_key,v_start,v_start+v_duration,1)
            on conflict(bucket_key,starts_at) do update set used=public_rate_buckets.used+1;
    end loop;
    select * into strict v_result from inquiry_private.submit_inquiry(
        p_request_id,p_snapshot,'public_form',null,null,'{}'::jsonb);
    return query select true,p_request_id,v_result.replayed;
end;
$$;
revoke all on function public.create_public_inquiry(uuid,jsonb,text,uuid)
    from public, anon, authenticated, service_role;
grant execute on function public.create_public_inquiry(uuid,jsonb,text,uuid) to anon;
commit;
