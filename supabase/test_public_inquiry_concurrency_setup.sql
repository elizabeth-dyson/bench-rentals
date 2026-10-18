-- TEST ONLY: disposable isolated project, owner. COMMITS synthetic fixtures.
-- Never production. Discard/reset the entire disposable project afterward.
-- Install 5.3 and 5.4 first. Run this setup once per fresh test project.
begin;
create schema public_inquiry_test;
revoke all on schema public_inquiry_test from public,anon,authenticated,service_role;
create table public_inquiry_test.fixture (
    singleton boolean primary key default true check(singleton),
    scenario text not null, request_id uuid not null, session_id uuid not null, snapshot jsonb not null
);
create table public_inquiry_test.results (
    scenario text not null, participant text not null, request_id uuid not null,
    replayed boolean, error_state text, elapsed_seconds numeric not null,
    primary key(scenario,participant)
);
insert into public_inquiry_test.fixture values(true,'retry',gen_random_uuid(),gen_random_uuid(),
    jsonb_build_object('schema_version',1,'answers',jsonb_build_object(
        'customer_name','Public concurrency fixture','event_date','2098-06-14','requested_bench_count',2,
        'preferred_contact_method','email','email',gen_random_uuid()::text||'@example.invalid',
        'phone',null,'facebook_identity',null,'event_type',null,'source',null,'venue',null,
        'delivery_preference','unsure','delivery_at',null,'setup_complete_by',null,'event_start_at',null,
        'pickup_at',null,'rehearsal_at',null,'timing_notes',null,'rental_notes',null,
        'delivery_instructions',null,'pickup_instructions',null)));

create function public_inquiry_test.prepare_case(p_case text) returns void language plpgsql as $$
begin
    if p_case not in ('retry','session','hour','day') then raise exception 'Unknown scenario'; end if;
    if exists(select 1 from public_inquiry_test.results where scenario=p_case) then
        raise exception 'Scenario already run. Use a fresh disposable project to repeat.';
    end if;
    update public_inquiry_test.fixture set scenario=p_case,request_id=gen_random_uuid(),session_id=gen_random_uuid();
    delete from inquiry_private.public_rate_buckets;
    update inquiry_private.public_config set enabled=true,
        gateway_secret_hash=encode(sha256(convert_to(repeat('a',43),'UTF8')),'hex'),
        session_limit=case when p_case='session' then 1 else 100 end,
        hourly_limit=case when p_case='hour' then 1 else 100 end,
        daily_limit=case when p_case='day' then 1 else 100 end;
end $$;

create function public_inquiry_test.run_case(p_participant text) returns void language plpgsql as $$
declare f record; r record; v_request uuid; v_session uuid; v_error text; v_replayed boolean;
    v_start timestamptz := clock_timestamp();
begin
    if p_participant not in ('A','B') then raise exception 'Unknown participant'; end if;
    select * into strict f from public_inquiry_test.fixture;
    -- Avoid a counter reset at a window boundary during the artificial lock delay.
    if extract(epoch from date_trunc('hour',clock_timestamp())+interval '1 hour'-clock_timestamp()) < 30
       or extract(epoch from date_bin(interval '15 minutes',clock_timestamp(),'2000-01-01'::timestamptz)+interval '15 minutes'-clock_timestamp()) < 30 then
        raise exception 'Too close to a time boundary. Retry after the next quarter hour.';
    end if;
    v_request := case when f.scenario='retry' or p_participant='A' then f.request_id else gen_random_uuid() end;
    v_session := case when f.scenario in ('retry','session') then f.session_id else gen_random_uuid() end;
    begin
        select * into strict r from public.create_public_inquiry(v_request,f.snapshot,repeat('a',43),v_session);
        v_replayed := r.replayed;
    exception when sqlstate 'P5401' then v_error := 'P5401';
    end;
    insert into public_inquiry_test.results values(f.scenario,p_participant,v_request,v_replayed,v_error,
        extract(epoch from clock_timestamp()-v_start));
    if p_participant='A' then perform pg_sleep(15); end if;
end $$;
revoke all on all tables in schema public_inquiry_test from public,anon,authenticated,service_role;
revoke all on all functions in schema public_inquiry_test from public,anon,authenticated,service_role;
select public_inquiry_test.prepare_case('retry');
commit;
select 'Run A then immediately B in separate sessions, then verify. Repeat with prepare_case for session, hour, day.' as next_step;
