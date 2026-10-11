-- TEST ONLY, DISPOSABLE isolated project, owner. This script COMMITS synthetic
-- fixtures so two sessions can see them. Never production. Reset/discard the test
-- project afterward; do not disable snapshot preservation to delete fixtures.
-- Run once per empty inquiry_pipeline_test schema. Set a synthetic Auth UUID.
begin;
set local request.jwt.claim.sub = '00000000-0000-4000-8000-000000000053';
do $$ begin
    if not exists(select 1 from auth.users where id=auth.uid()) then
        raise exception 'Set a synthetic test Auth UUID first.';
    end if;
    if to_regnamespace('inquiry_pipeline_test') is not null then
        raise exception 'Use a fresh disposable project or reset the test environment before repeating.';
    end if;
end $$;
create schema inquiry_pipeline_test;
revoke all on schema inquiry_pipeline_test from public, anon, authenticated, service_role;
create table inquiry_pipeline_test.fixture (
    singleton boolean primary key default true check(singleton), actor uuid not null,
    shared_request uuid not null, shared_answers jsonb not null,
    matching_answers jsonb not null, numbering_answers jsonb not null, target_booking uuid not null
);
create table inquiry_pipeline_test.results (
    scenario text not null, session_name text not null, booking_id uuid not null,
    booking_number text not null, submission_id uuid not null, submission_number integer not null,
    replayed boolean not null, elapsed_seconds numeric not null, primary key(scenario,session_name)
);
do $$
declare v_base jsonb; v_booking uuid;
begin
    v_base := jsonb_build_object('schema_version',1,'answers',jsonb_build_object(
        'customer_name','Concurrency fixture','event_date','2097-06-14','requested_bench_count',2,
        'preferred_contact_method','email','email',gen_random_uuid()::text || '@example.invalid',
        'phone',null,'facebook_identity',null,'event_type',null,'source',null,'venue',null,
        'delivery_preference','unsure','delivery_at',null,'setup_complete_by',null,
        'event_start_at',null,'pickup_at',null,'rehearsal_at',null,'timing_notes',null,
        'rental_notes',null,'delivery_instructions',null,'pickup_instructions',null));
    select booking_id into v_booking from public.create_lead('Concurrency legacy fixture','2097-06-14',2,'email','other',
        gen_random_uuid()::text || '@example.invalid',null,null,null,null,null,null,null);
    insert into inquiry_pipeline_test.fixture(actor,shared_request,shared_answers,matching_answers,numbering_answers,target_booking)
    values(auth.uid(),gen_random_uuid(),v_base,
        jsonb_set(v_base,'{answers,email}',to_jsonb(gen_random_uuid()::text || '@example.invalid')),
        jsonb_set(v_base,'{answers,email}',to_jsonb(gen_random_uuid()::text || '@example.invalid')),v_booking);
end $$;

-- Owner-controlled orchestration only. Real auth wrappers still derive actor
-- from request context. Not granted to any application role or exposed schema.
create function inquiry_pipeline_test.run_case(p_case text,p_session text) returns void
language plpgsql security invoker as $$
declare v_fixture inquiry_pipeline_test.fixture%rowtype; v_request uuid; v_snapshot jsonb;
    v_result record; v_start timestamptz; v_elapsed numeric;
begin
    select * into strict v_fixture from inquiry_pipeline_test.fixture;
    perform set_config('request.jwt.claim.sub',v_fixture.actor::text,true);
    v_request := case when p_case='retry' then v_fixture.shared_request else gen_random_uuid() end;
    v_snapshot := case p_case when 'retry' then v_fixture.shared_answers
        when 'matching' then v_fixture.matching_answers else v_fixture.numbering_answers end;
    if p_case='numbering' then
        v_snapshot := jsonb_set(v_snapshot,'{answers,email}',to_jsonb(gen_random_uuid()::text || '@example.invalid'));
    end if;
    v_start := clock_timestamp();
    if p_case='followup' then
        select * into v_result from public.append_staff_inquiry_submission(v_request,v_fixture.target_booking,v_snapshot);
    else
        select * into v_result from public.create_staff_inquiry(v_request,v_snapshot);
    end if;
    v_elapsed := extract(epoch from clock_timestamp()-v_start);
    insert into inquiry_pipeline_test.results values(p_case,p_session,v_result.booking_id,v_result.booking_number,
        v_result.submission_id,v_result.submission_number,v_result.replayed,v_elapsed);
    -- Hold transaction locks so session B must contend. This is test-only.
    if p_session='A' then perform pg_sleep(15); end if;
end $$;
revoke all on all functions in schema inquiry_pipeline_test from public,anon,authenticated,service_role;
commit;
select 'Setup committed. Run session A and immediately session B in separate SQL Editor sessions.' as next_step;
