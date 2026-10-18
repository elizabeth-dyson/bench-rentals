-- TEST ONLY: one-transaction smoke check for the existing Supabase project.
-- Run as SQL Editor owner BEFORE enabling public sharing, with enabled=false.
-- This temporarily changes the gateway hash/limits and creates synthetic
-- inquiry records, then ROLLBACK removes every change. Never run after launch.
-- Run the COMPLETE file in one SQL Editor execution. On any error run ROLLBACK.
begin;
set local statement_timeout = '20s';
set local lock_timeout = '5s';

do $$
begin
    if (select count(*) from inquiry_private.public_config) <> 1
       or (select enabled from inquiry_private.public_config where singleton) is distinct from false then
        raise exception 'Public access must be disabled before this rollback-only check.';
    end if;
end $$;

create temp table public_inquiry_smoke (
    request_id uuid not null,
    session_id uuid not null,
    snapshot jsonb not null
);
insert into public_inquiry_smoke
select gen_random_uuid(), gen_random_uuid(), jsonb_build_object(
    'schema_version',1,'answers',jsonb_build_object(
        'customer_name','Rollback-only inquiry fixture',
        'event_date','2098-06-14','requested_bench_count',2,
        'preferred_contact_method','email',
        'email',gen_random_uuid()::text || '@example.invalid',
        'phone',null,'facebook_identity',null,'event_type',null,
        'source',null,'venue',null,'delivery_preference','unsure',
        'delivery_at',null,'setup_complete_by',null,'event_start_at',null,
        'pickup_at',null,'rehearsal_at',null,'timing_notes',null,
        'rental_notes',null,'delivery_instructions',null,
        'pickup_instructions',null));
grant select on public_inquiry_smoke to anon;

-- This test credential is never committed or used by the app.
update inquiry_private.public_config
set gateway_secret_hash=encode(sha256(convert_to(repeat('a',43),'UTF8')),'hex'),
    enabled=true, session_limit=1, hourly_limit=100, daily_limit=100
where singleton;
delete from inquiry_private.public_rate_buckets;

set local role anon;
do $$
declare
    v_fixture record;
    v_first record;
    v_retry record;
    v_rejected boolean;
begin
    select * into strict v_fixture from public_inquiry_smoke;

    v_rejected := false;
    begin
        perform public.create_public_inquiry(v_fixture.request_id,v_fixture.snapshot,
            repeat('b',43),v_fixture.session_id);
    exception when insufficient_privilege then v_rejected := true;
    end;
    if not v_rejected then raise exception 'Wrong gateway credential was accepted.'; end if;

    select * into strict v_first from public.create_public_inquiry(
        v_fixture.request_id,v_fixture.snapshot,repeat('a',43),v_fixture.session_id);
    if v_first.accepted is distinct from true or v_first.replayed is distinct from false
       or v_first.request_id <> v_fixture.request_id then
        raise exception 'Initial public receipt was invalid.';
    end if;

    select * into strict v_retry from public.create_public_inquiry(
        v_fixture.request_id,v_fixture.snapshot,repeat('a',43),v_fixture.session_id);
    if v_retry.accepted is distinct from true or v_retry.replayed is distinct from true
       or v_retry.request_id <> v_fixture.request_id then
        raise exception 'Identical retry did not replay.';
    end if;

    v_rejected := false;
    begin
        perform public.create_public_inquiry(gen_random_uuid(),v_fixture.snapshot,
            repeat('a',43),v_fixture.session_id);
    exception when sqlstate 'P5401' then v_rejected := true;
    end;
    if not v_rejected then raise exception 'Session budget was not enforced.'; end if;
end $$;
reset role;

do $$
declare v_request uuid;
begin
    select request_id into strict v_request from public_inquiry_smoke;
    if (select count(*) from public.intake_submissions where request_id=v_request) <> 1
       or (select count(*) from inquiry_private.public_rate_buckets) <> 3
       or (select sum(used) from inquiry_private.public_rate_buckets) <> 3 then
        raise exception 'Expected one inquiry and three one-use rate buckets.';
    end if;
    if not exists(select 1 from public.intake_submissions s
        join public.bookings b on b.id=s.booking_id
        where s.request_id=v_request and s.entry_method='public_form'
          and s.submitted_by is null and s.review_status='pending'
          and b.stage='lead' and b.entry_method='public_form') then
        raise exception 'Saved inquiry provenance or stage was invalid.';
    end if;
    raise notice 'PASS: anonymous create/retry/limit checks completed. Rolling back all fixtures.';
end $$;
rollback;
