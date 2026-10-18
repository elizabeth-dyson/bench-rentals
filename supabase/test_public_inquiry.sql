-- TEST ONLY: isolated Supabase project, SQL Editor owner. NEVER production.
-- Requires 5.3 + both 5.4 installers. All fixtures and configuration roll back.
-- On error issue ROLLBACK; psql users set ON_ERROR_STOP=1.
begin;
create function pg_temp.check_true(p_test boolean,p_message text) returns void language plpgsql as $$
begin if p_test is distinct from true then raise exception 'FAILED: %',p_message; end if; end $$;
create function pg_temp.expect_error(p_sql text,p_state text) returns void language plpgsql as $$
declare v_state text;
begin
    begin execute p_sql;
    exception when others then
        get stacked diagnostics v_state=returned_sqlstate;
        if v_state=p_state then return; end if;
        raise exception 'Expected %, got %',p_state,v_state;
    end;
    raise exception 'Expected %, statement succeeded',p_state;
end $$;
create function pg_temp.answers(p_email text) returns jsonb language sql as $$
select jsonb_build_object('schema_version',1,'answers',jsonb_build_object(
    'customer_name','  Public fixture  ','event_date','2020-06-14','requested_bench_count',30,
    'preferred_contact_method','email','email',p_email,'phone',null,'facebook_identity',null,
    'event_type',null,'source',null,'venue',null,'delivery_preference','unsure',
    'delivery_at',null,'setup_complete_by',null,'event_start_at',null,'pickup_at',null,'rehearsal_at',null,
    'timing_notes',null,'rental_notes',' Original ','delivery_instructions',null,'pickup_instructions',null))
$$;
create temp table public_fixture(request_id uuid,session_id uuid,snapshot jsonb);
insert into public_fixture values(gen_random_uuid(),gen_random_uuid(),pg_temp.answers(gen_random_uuid()::text||'@example.invalid'));
grant select on public_fixture to anon;
update inquiry_private.public_config set enabled=true,
    gateway_secret_hash=encode(sha256(convert_to(repeat('a',43),'UTF8')),'hex'),
    session_limit=5,hourly_limit=30,daily_limit=100;
delete from inquiry_private.public_rate_buckets;

set local role anon;
select pg_temp.expect_error('select * from inquiry_private.public_config','42501');
select pg_temp.expect_error('select * from inquiry_private.public_rate_buckets','42501');
select pg_temp.expect_error($q$select * from inquiry_private.submit_inquiry(gen_random_uuid(),'{}','public_form',null)$q$,'42501');
select pg_temp.expect_error($q$select * from public.create_staff_inquiry(gen_random_uuid(),'{}')$q$,'42501');
select pg_temp.expect_error($q$insert into public.customers(preferred_name) values('Forbidden public write')$q$,'42501');
do $$
declare f record; r record; again record;
begin
    select * into f from public_fixture;
    perform pg_temp.expect_error(format('select * from public.create_public_inquiry(%L,%L,null,%L)',f.request_id,f.snapshot,f.session_id),'42501');
    perform pg_temp.expect_error(format('select * from public.create_public_inquiry(%L,%L,%L,%L)',f.request_id,f.snapshot,repeat('b',43),f.session_id),'42501');
    select * into r from public.create_public_inquiry(f.request_id,f.snapshot,repeat('a',43),f.session_id);
    perform pg_temp.check_true(to_jsonb(r)=jsonb_build_object('accepted',true,'request_id',f.request_id,'replayed',false),'minimal receipt');
    select * into again from public.create_public_inquiry(f.request_id,f.snapshot,repeat('a',43),f.session_id);
    perform pg_temp.check_true(again.replayed,'identical retry');
    perform pg_temp.expect_error(format('select * from public.create_public_inquiry(%L,%L,%L,%L)',
        f.request_id,jsonb_set(f.snapshot,'{answers,customer_name}','"Changed"'),repeat('a',43),f.session_id),'P5104');
    perform pg_temp.expect_error(format('select * from public.create_public_inquiry(%L,%L,%L,%L)',
        gen_random_uuid(),jsonb_set(f.snapshot,'{answers,internal_notes}','"Forbidden"'),repeat('a',43),f.session_id),'P5101');
    perform pg_temp.expect_error(format('select * from public.create_public_inquiry(%L,%L,%L,%L)',
        gen_random_uuid(),jsonb_set(f.snapshot,'{answers,customer_name}',to_jsonb(repeat('x',201))),repeat('a',43),f.session_id),'P5101');
    -- Default RLS may produce zero visible rows or privilege denial; either is safe.
    begin
        perform pg_temp.check_true((select count(*)=0 from public.intake_submissions where request_id=f.request_id),'no submission read');
        perform pg_temp.check_true((select count(*)=0 from public.customers where email=f.snapshot->'answers'->>'email'),'no customer search');
    exception when insufficient_privilege then null; end;
end $$;
reset role;

select pg_temp.check_true((select count(*)=1 from public.intake_submissions s join public_fixture f using(request_id)), 'one submission');
select pg_temp.check_true((select s.submitted_data=f.snapshot and s.entry_method='public_form'
    and s.submitted_by is null and s.review_status='pending' and s.intake_link_id is null
    and b.stage='lead' and b.entry_method='public_form' and b.created_by is null
    and b.internal_notes is null and b.inventory_out_at is null and b.confirmed_bench_count is null
    from public.intake_submissions s join public_fixture f using(request_id) join public.bookings b on b.id=s.booking_id), 'atomic public provenance');
select pg_temp.check_true((select count(*)=3 and sum(used)=3 from inquiry_private.public_rate_buckets),'retry did not consume budget');

-- Closed records still replay, but authorization is checked every time.
update public.bookings b set stage='cancelled' from public.intake_submissions s,public_fixture f
    where b.id=s.booking_id and s.request_id=f.request_id;
set local role anon;
select pg_temp.check_true((select r.replayed from public_fixture f cross join lateral public.create_public_inquiry(
    f.request_id,f.snapshot,repeat('a',43),f.session_id) r),'closed replay');
reset role;
update inquiry_private.public_config set enabled=false;
set local role anon;
select pg_temp.expect_error(format('select * from public.create_public_inquiry(%L,%L,%L,%L)',request_id,snapshot,repeat('a',43),session_id),'42501') from public_fixture;
reset role;
update inquiry_private.public_config set enabled=true;

-- Exact matching preserves the entire existing profile and records original answers.
update public.customers c set preferred_name='Preserve profile',notes='Private customer notes'
    from public.bookings b,public.intake_submissions s,public_fixture f
    where c.id=b.primary_customer_id and b.id=s.booking_id and s.request_id=f.request_id;
set local role anon;
select * from public_fixture f cross join lateral public.create_public_inquiry(gen_random_uuid(),f.snapshot,repeat('a',43),f.session_id);
reset role;
select pg_temp.check_true((select count(*)=1 from public.customers c,public_fixture f
    where c.email=f.snapshot->'answers'->>'email' and c.preferred_name='Preserve profile' and c.notes='Private customer notes'), 'matching preserves profile');
select pg_temp.check_true(exists(select 1 from public.intake_submissions s,public_fixture f
    where s.submitted_data=f.snapshot and s.customer_match_outcome='reused_exact'), 'exact matching');

-- Force the final insert to fail: all customer/booking/counter changes roll back.
create function pg_temp.fail_public_insert() returns trigger language plpgsql as $$
begin raise exception 'Synthetic insert failure' using errcode='P5499'; end $$;
create trigger test_fail_public_insert before insert on public.intake_submissions for each row execute function pg_temp.fail_public_insert();
create temp table before_failure as select (select count(*) from public.customers) customers,
    (select count(*) from public.bookings) bookings,(select sum(used) from inquiry_private.public_rate_buckets) used;
set local role anon;
select pg_temp.expect_error(format('select * from public.create_public_inquiry(%L,%L,%L,%L)',gen_random_uuid(),
    pg_temp.answers(gen_random_uuid()::text||'@example.invalid'),repeat('a',43),gen_random_uuid()),'P5499');
reset role;
drop trigger test_fail_public_insert on public.intake_submissions;
select pg_temp.check_true((select customers=(select count(*) from public.customers)
    and bookings=(select count(*) from public.bookings) and used=(select sum(used) from inquiry_private.public_rate_buckets)
    from before_failure),'failed insert rolls back records and budgets');

-- Test every budget independently; rejection leaves no partial budget increments.
do $$
declare i integer; j integer; f record; before_count integer;
begin
    select * into f from public_fixture;
    for i in 1..3 loop
        delete from inquiry_private.public_rate_buckets;
        update inquiry_private.public_config set session_limit=case when i=1 then 1 else 100 end,
            hourly_limit=case when i=2 then 1 else 100 end,daily_limit=case when i=3 then 1 else 100 end;
        perform public.create_public_inquiry(gen_random_uuid(),f.snapshot,repeat('a',43),f.session_id);
        select count(*) into before_count from public.intake_submissions;
        perform pg_temp.expect_error(format('select * from public.create_public_inquiry(%L,%L,%L,%L)',gen_random_uuid(),
            f.snapshot,repeat('a',43),case when i=1 then f.session_id else gen_random_uuid() end),'P5401');
        perform pg_temp.check_true((select count(*)=before_count from public.intake_submissions),'throttle creates no records');
        perform pg_temp.check_true((select sum(used)=3 from inquiry_private.public_rate_buckets),'throttle rolls back budget');
        perform pg_temp.check_true((select r.replayed from public.create_public_inquiry(f.request_id,f.snapshot,repeat('a',43),f.session_id) r),'retry at limit');
    end loop;
end $$;
rollback;
select 'PASS: public inquiry behavior/access tests completed and rolled back.' as result;
