-- TEST ONLY: isolated Supabase project, SQL Editor owner. NEVER production.
-- Install Phase 5.1 and both Phase 5.3 files first. Replace the synthetic Auth
-- UUID below. Every fixture/temporary helper/trigger is rolled back at the end.
-- On any error issue ROLLBACK; with psql use ON_ERROR_STOP=1.
begin;
set local request.jwt.claim.sub = '00000000-0000-4000-8000-000000000053';
do $$ begin
    if not exists(select 1 from auth.users where id = auth.uid()) then
        raise exception 'Replace request.jwt.claim.sub with a synthetic Auth user from this isolated project.';
    end if;
end $$;

create function pg_temp.check_true(p_test boolean, p_message text) returns void language plpgsql as $$
begin if p_test is distinct from true then raise exception 'FAILED: %', p_message; end if; end $$;

create function pg_temp.expect_error(p_sql text, p_state text) returns void language plpgsql as $$
declare v_state text;
begin
    begin execute p_sql;
    exception when others then
        get stacked diagnostics v_state = returned_sqlstate;
        if v_state = p_state then return; end if;
        raise exception 'Expected SQLSTATE %, received %', p_state, v_state;
    end;
    raise exception 'Expected SQLSTATE %, but statement succeeded', p_state;
end $$;

create function pg_temp.answers(p_email text) returns jsonb language sql as $$
    select jsonb_build_object('schema_version',1,'answers',jsonb_build_object(
        'customer_name','  Pipeline fixture  ','event_date','2098-06-14','requested_bench_count',12,
        'preferred_contact_method','email','email',p_email,'phone',null,'facebook_identity',null,
        'event_type',' Party ','source',null,'venue',null,'delivery_preference','unsure',
        'delivery_at',null,'setup_complete_by',null,'event_start_at',null,'pickup_at',null,'rehearsal_at',null,
        'timing_notes',null,'rental_notes',' Rental only ','delivery_instructions',null,'pickup_instructions',null))
$$;

-- Authenticated wrapper, complete persistence, retries, immutable metadata, follow-ups.
set local role authenticated;
do $$
declare
    v_request uuid := gen_random_uuid(); v_append uuid := gen_random_uuid();
    v_email text := gen_random_uuid()::text || '@example.invalid';
    v_snapshot jsonb; v_result record; v_again record; v_follow record; v_legacy record;
    v_booking_before jsonb; v_customer_before jsonb; v_venue_before jsonb;
    v_id uuid; v_other uuid; v_field text; v_bad jsonb; v_original jsonb;
begin
    v_snapshot := pg_temp.answers('  ' || upper(v_email) || '  ');
    v_snapshot := jsonb_set(v_snapshot,'{answers,venue}',
        '{"name":" Hall ","address_line_1":null,"address_line_2":null,"city":" Omaha ","state":null,"postal_code":null}');
    v_snapshot := jsonb_set(v_snapshot,'{answers,delivery_preference}','"parent_delivery"');
    v_snapshot := jsonb_set(v_snapshot,'{answers,delivery_at}','"2098-06-14T10:00:00-05:00"');
    v_snapshot := jsonb_set(v_snapshot,'{answers,pickup_at}','"2098-06-15T10:00:00-05:00"');
    v_snapshot := jsonb_set(v_snapshot,'{answers,setup_complete_by}','"2098-06-14T11:00:00-05:00"');
    v_snapshot := jsonb_set(v_snapshot,'{answers,event_start_at}','"2098-06-14T12:00:00-05:00"');
    v_snapshot := jsonb_set(v_snapshot,'{answers,rehearsal_at}','"2098-06-13T12:00:00-05:00"');
    v_snapshot := jsonb_set(v_snapshot,'{answers,timing_notes}','" Requested timing "');
    v_snapshot := jsonb_set(v_snapshot,'{answers,delivery_instructions}','" Side door "');
    v_snapshot := jsonb_set(v_snapshot,'{answers,pickup_instructions}','" Call first "');
    select * into v_result from public.create_staff_inquiry(v_request,v_snapshot,'{"internal_notes":" Staff only "}');
    perform pg_temp.check_true(v_result.submission_number = 1 and not v_result.replayed,'initial receipt');
    perform pg_temp.check_true(exists(select 1 from public.bookings b join public.customers c on c.id=b.primary_customer_id
        join public.venues v on v.id=b.venue_id where b.id=v_result.booking_id
        and b.stage='lead' and b.entry_method='staff_entered' and b.created_by=auth.uid()
        and b.source='other' and b.event_type='Party' and b.requested_bench_count=12
        and b.customer_notes='Rental only' and b.internal_notes='Staff only' and c.notes is null
        and c.email=v_email and c.preferred_name='Pipeline fixture' and v.city='Omaha' and v.state is null
        and b.delivery_method='parent_delivery' and b.delivery_at='2098-06-14T15:00:00Z'::timestamptz
        and b.pickup_at='2098-06-15T15:00:00Z'::timestamptz
        and b.setup_complete_by='2098-06-14T16:00:00Z'::timestamptz
        and b.event_start_at='2098-06-14T17:00:00Z'::timestamptz
        and b.rehearsal_at='2098-06-13T17:00:00Z'::timestamptz and b.timing_notes='Requested timing'
        and b.delivery_instructions='Side door' and b.pickup_instructions='Call first'
        and b.inventory_out_at is null and b.inventory_return_at is null and b.confirmed_bench_count is null),'field mapping');
    perform pg_temp.check_true(exists(select 1 from public.booking_contacts c where c.booking_id=v_result.booking_id
        and c.contact_role='primary_customer' and c.is_primary),'primary relationship');
    perform pg_temp.check_true(exists(select 1 from public.intake_submissions s where s.id=v_result.submission_id
        and s.submitted_data=v_snapshot and s.entry_method='staff_entered' and s.submitted_by=auth.uid()
        and s.review_status='pending' and s.customer_match_outcome='new_customer'),'original snapshot/provenance');
    select * into v_again from public.create_staff_inquiry(v_request,v_snapshot,'{"internal_notes":" Staff only "}');
    perform pg_temp.check_true(v_again.replayed and v_again.submission_id=v_result.submission_id,'same-key replay');
    perform pg_temp.expect_error(format('select * from public.create_staff_inquiry(%L,%L::jsonb)',v_request,v_snapshot),'P5104');
    perform pg_temp.expect_error(format('select * from public.create_staff_inquiry(%L,%L::jsonb,%L::jsonb)',
        v_request,jsonb_set(v_snapshot,'{answers,customer_name}','"Changed"'),'{"internal_notes":" Staff only "}'),'P5104');
    perform pg_temp.expect_error(format('select * from public.append_staff_inquiry_submission(%L,%L,%L::jsonb)',
        v_request,v_result.booking_id,v_snapshot),'P5104');

    select to_jsonb(b),to_jsonb(c),to_jsonb(v) into v_booking_before,v_customer_before,v_venue_before
    from public.bookings b join public.customers c on c.id=b.primary_customer_id join public.venues v on v.id=b.venue_id
    where b.id=v_result.booking_id;
    select * into v_follow from public.append_staff_inquiry_submission(v_append,v_result.booking_id,
        jsonb_set(v_snapshot,'{answers,requested_bench_count}','30'));
    perform pg_temp.check_true(v_follow.submission_number=2 and v_follow.booking_number=v_result.booking_number,'follow-up identifiers');
    perform pg_temp.check_true(exists(select 1 from public.bookings b join public.customers c on c.id=b.primary_customer_id
        join public.venues v on v.id=b.venue_id where b.id=v_result.booking_id and to_jsonb(b)=v_booking_before
        and to_jsonb(c)=v_customer_before and to_jsonb(v)=v_venue_before),'follow-up leaves all working records unchanged');
    update public.bookings set stage='lost' where id=v_result.booking_id;
    select * into v_again from public.append_staff_inquiry_submission(v_append,v_result.booking_id,
        jsonb_set(v_snapshot,'{answers,requested_bench_count}','30'));
    perform pg_temp.check_true(v_again.replayed and v_again.submission_id=v_follow.submission_id,'replay after closing');
    perform pg_temp.expect_error(format('select * from public.append_staff_inquiry_submission(%L,%L,%L::jsonb)',
        gen_random_uuid(),v_result.booking_id,v_snapshot),'P5103');
    update public.bookings set stage='cancelled' where id=v_result.booking_id;
    perform pg_temp.expect_error(format('select * from public.append_staff_inquiry_submission(%L,%L,%L::jsonb)',
        gen_random_uuid(),v_result.booking_id,v_snapshot),'P5103');
    perform pg_temp.expect_error(format('select * from public.append_staff_inquiry_submission(%L,%L,%L::jsonb)',
        gen_random_uuid(),gen_random_uuid(),v_snapshot),'P5102');
    perform pg_temp.expect_error(format('select * from public.create_staff_inquiry(%L,%L::jsonb,%L::jsonb)',
        gen_random_uuid(),v_snapshot,jsonb_build_object('existing_customer_id',gen_random_uuid())),'P5102');

    foreach v_field in array array['request_id','request_fingerprint','customer_match_outcome','submitted_data',
        'booking_id','submission_number','submitted_at','entry_method','submitted_by','intake_link_id','id'] loop
        perform pg_temp.expect_error(format('update public.intake_submissions set %I = %s where id=%L',v_field,
            case v_field
                when 'request_id' then 'gen_random_uuid()' when 'request_fingerprint' then quote_literal(repeat('a',64))
                when 'customer_match_outcome' then quote_literal('needs_review') when 'submitted_data' then '''{}''::jsonb'
                when 'submission_number' then '99' when 'submitted_at' then 'submitted_at + interval ''1 second'''
                when 'entry_method' then quote_literal('public_form') else 'gen_random_uuid()' end,v_result.submission_id),'23514');
    end loop;
    perform pg_temp.expect_error(format('delete from public.intake_submissions where id=%L',v_result.submission_id),'23514');
    perform pg_temp.expect_error('truncate public.intake_submissions','23514');
    update public.intake_submissions set review_status='accepted', reviewed_by=auth.uid(), reviewed_at=now(), review_notes='Reviewed'
    where id=v_result.submission_id;
    perform pg_temp.check_true(exists(select 1 from public.intake_submissions where id=v_result.submission_id and review_status='accepted'
        and submitted_data=v_snapshot),'review metadata remains editable');
    perform pg_temp.expect_error(format('insert into public.intake_submissions(booking_id,submission_number,submitted_data,request_id,request_fingerprint)
        values(%L,99,''{}'',%L,%L)',v_result.booking_id,v_request,repeat('b',64)),'23505');
    perform pg_temp.expect_error(format('insert into public.intake_submissions(booking_id,submission_number,submitted_data,request_id)
        values(%L,99,''{}'',%L)',v_result.booking_id,gen_random_uuid()),'23514');

    select * into v_legacy from public.create_lead('Legacy fixture','2098-07-01',2,'email','other',
        gen_random_uuid()::text || '@example.invalid',null,null,null,null,null,null,null);
    update public.bookings set entry_method=null where id=v_legacy.booking_id;
    select * into v_again from public.append_staff_inquiry_submission(gen_random_uuid(),v_legacy.booking_id,v_snapshot);
    perform pg_temp.check_true(v_again.submission_number=1 and v_again.booking_number=v_legacy.booking_number
        and exists(select 1 from public.bookings where id=v_legacy.booking_id and entry_method is null),'legacy follow-up without backfill');

    -- Strict server validation, not just Python validation.
    v_original := pg_temp.answers(v_email);
    for v_bad in select value from jsonb_array_elements(jsonb_build_array(
        jsonb_set(v_original,'{schema_version}','2'), v_original || '{"staff_id":"bad"}'::jsonb,
        jsonb_set(v_original,'{answers}',(v_original->'answers') || '{"internal_notes":"bad"}'::jsonb),
        v_original #- '{answers,customer_name}', jsonb_set(v_original,'{answers,customer_name}','" "'),
        jsonb_set(v_original,'{answers,event_date}','"2098-02-30"'),
        jsonb_set(v_original,'{answers,requested_bench_count}','true'),
        jsonb_set(v_original,'{answers,requested_bench_count}','1.5'),
        jsonb_set(v_original,'{answers,requested_bench_count}','0'),
        jsonb_set(v_original,'{answers,preferred_contact_method}','"phone"'),
        jsonb_set(v_original,'{answers,email}','"bad"'),
        jsonb_set(v_original,'{answers,phone}','"abc"'),
        jsonb_set(v_original,'{answers,source}','"invalid"'),
        jsonb_set(v_original,'{answers,delivery_preference}','"third_party"'),
        jsonb_set(v_original,'{answers,venue}','{"city":1}'),
        jsonb_set(v_original,'{answers,delivery_at}','"2098-06-14T10:00:00"'),
        jsonb_set(v_original,'{answers,delivery_at}','"2098-06-14T24:00:00Z"'),
        jsonb_set(v_original,'{answers,delivery_at}','"2098-02-30T10:00:00Z"'),
        jsonb_set(jsonb_set(v_original,'{answers,delivery_at}','"2098-06-15T10:00:00Z"'),'{answers,pickup_at}','"2098-06-14T10:00:00Z"')
    )) loop
        perform pg_temp.expect_error(format('select * from public.create_staff_inquiry(%L,%L::jsonb)',gen_random_uuid(),v_bad),'P5101');
    end loop;
    perform pg_temp.expect_error(format('select * from public.create_staff_inquiry(%L,%L::jsonb,''{"customer_profile_notes":"bad"}'')',gen_random_uuid(),v_original),'P5101');
end $$;
reset role;

-- Owner-only public-origin branch. No public endpoint is granted by these tests.
do $$
declare
    v_email text := gen_random_uuid()::text || '@example.invalid';
    v_snapshot jsonb; v_customer uuid; v_second uuid; v_profile jsonb;
    v_result record; v_reused record; v_follow record; v_case text; v_fb text := gen_random_uuid()::text;
    v_request uuid := gen_random_uuid();
begin
    insert into public.customers(preferred_name,email,phone,preferred_contact_method,notes)
    values('Existing profile',v_email,'(402) 555-0199','phone','Preserve profile notes') returning id into v_customer;
    insert into public.customer_identities(customer_id,identity_type,display_value) values(v_customer,'facebook','  ' || upper(v_fb) || '  ');
    select to_jsonb(c) into v_profile from public.customers c where id=v_customer;
    v_snapshot := pg_temp.answers(upper(v_email));
    select * into v_result from inquiry_private.submit_inquiry(v_request,v_snapshot,'public_form',null);
    perform pg_temp.check_true(exists(select 1 from public.bookings where id=v_result.booking_id and primary_customer_id=v_customer
        and created_by is null and entry_method='public_form' and venue_id is null and delivery_method is null),'public exact reuse');
    perform pg_temp.check_true(exists(select 1 from public.intake_submissions where id=v_result.submission_id and submitted_by is null
        and entry_method='public_form' and customer_match_outcome='reused_exact'),'public provenance');
    perform pg_temp.check_true((select to_jsonb(c)=v_profile from public.customers c where id=v_customer),'reused profile untouched');
    select * into v_reused from inquiry_private.submit_inquiry(v_request,v_snapshot,'public_form',null);
    perform pg_temp.check_true(v_reused.replayed and v_reused.submission_id=v_result.submission_id,'public retry');
    perform pg_temp.expect_error(format('select * from public.create_staff_inquiry(%L,%L::jsonb)',v_request,v_snapshot),'P5104');
    foreach v_case in array array['phone','text','facebook'] loop
        v_snapshot := jsonb_set(pg_temp.answers(null),'{answers,preferred_contact_method}',to_jsonb(v_case));
        if v_case = 'facebook' then v_snapshot := jsonb_set(v_snapshot,'{answers,facebook_identity}',to_jsonb(v_fb));
        else v_snapshot := jsonb_set(v_snapshot,'{answers,phone}','"4025550199"'); end if;
        select * into v_reused from inquiry_private.submit_inquiry(gen_random_uuid(),v_snapshot,'public_form',null);
        perform pg_temp.check_true(exists(select 1 from public.bookings where id=v_reused.booking_id and primary_customer_id=v_customer),'normalized contact reuse');
    end loop;
    v_snapshot := jsonb_set(pg_temp.answers(v_email),'{answers,phone}','"4025550199"');
    v_snapshot := jsonb_set(v_snapshot,'{answers,facebook_identity}',to_jsonb(v_fb));
    select * into v_reused from inquiry_private.submit_inquiry(gen_random_uuid(),v_snapshot,'public_form',null);
    perform pg_temp.check_true(exists(select 1 from public.bookings where id=v_reused.booking_id and primary_customer_id=v_customer),'all contacts consistent');
    insert into public.customers(preferred_name,phone,preferred_contact_method)
    values('Different contact owner','4025550177','phone') returning id into v_second;
    v_snapshot := jsonb_set(pg_temp.answers(v_email),'{answers,phone}','"4025550177"');
    select * into v_reused from inquiry_private.submit_inquiry(gen_random_uuid(),v_snapshot,'public_form',null);
    perform pg_temp.check_true(exists(select 1 from public.intake_submissions where id=v_reused.submission_id and customer_match_outcome='needs_review')
        and exists(select 1 from public.bookings where id=v_reused.booking_id and primary_customer_id not in (v_customer,v_second)),
        'conflicting contact owners need review');
    v_snapshot := jsonb_set(pg_temp.answers(v_email),'{answers,phone}','"4025550188"');
    select * into v_reused from inquiry_private.submit_inquiry(gen_random_uuid(),v_snapshot,'public_form',null);
    perform pg_temp.check_true(exists(select 1 from public.intake_submissions where id=v_reused.submission_id and customer_match_outcome='needs_review')
        and exists(select 1 from public.bookings where id=v_reused.booking_id and primary_customer_id<>v_customer),'unmatched extra contact needs review');
    -- Email now matches multiple active customers; no automatic merge.
    select * into v_reused from inquiry_private.submit_inquiry(gen_random_uuid(),pg_temp.answers(v_email),'public_form',null);
    perform pg_temp.check_true(exists(select 1 from public.intake_submissions where id=v_reused.submission_id and customer_match_outcome='needs_review'),'ambiguous contact');
    select * into v_reused from public.create_staff_inquiry(gen_random_uuid(),pg_temp.answers(gen_random_uuid()::text || '@example.invalid'),
        jsonb_build_object('existing_customer_id',v_customer));
    perform pg_temp.check_true(exists(select 1 from public.intake_submissions where id=v_reused.submission_id and customer_match_outcome='selected_by_staff')
        and (select to_jsonb(c)=v_profile from public.customers c where id=v_customer),'explicit staff reuse preserves profile');
    select * into v_follow from inquiry_private.submit_inquiry(gen_random_uuid(),pg_temp.answers(v_email),'public_form',null,v_reused.booking_id);
    perform pg_temp.check_true(v_follow.submission_number=2
        and exists(select 1 from public.bookings where id=v_reused.booking_id and entry_method='staff_entered')
        and exists(select 1 from public.intake_submissions where id=v_follow.submission_id and entry_method='public_form'
            and customer_match_outcome is null and submitted_by is null),'independent follow-up origin');
    update public.customers set is_archived=true where id=v_customer;
    perform pg_temp.expect_error(format('select * from public.create_staff_inquiry(%L,%L::jsonb,%L::jsonb)',gen_random_uuid(),pg_temp.answers(v_email),
        jsonb_build_object('existing_customer_id',v_customer)),'P5102');
    perform pg_temp.expect_error(format('select * from inquiry_private.submit_inquiry(%L,%L::jsonb,''public_form'',null,null,''{"internal_notes":"bad"}'')',
        gen_random_uuid(),pg_temp.answers(v_email)),'P5101');
    perform pg_temp.expect_error(format('select * from inquiry_private.submit_inquiry(%L,%L::jsonb,''public_form'',%L)',
        gen_random_uuid(),pg_temp.answers(v_email),auth.uid()),'42501');
    -- Archived-only contact does not cause reuse; unknown venue stays unlinked.
    v_snapshot := jsonb_set(pg_temp.answers(null),'{answers,preferred_contact_method}','"facebook"');
    v_snapshot := jsonb_set(v_snapshot,'{answers,facebook_identity}',to_jsonb(v_fb));
    v_snapshot := jsonb_set(v_snapshot,'{answers,delivery_preference}','"customer_pickup"');
    select * into v_reused from inquiry_private.submit_inquiry(gen_random_uuid(),v_snapshot,'public_form',null);
    perform pg_temp.check_true(exists(select 1 from public.intake_submissions where id=v_reused.submission_id and customer_match_outcome='new_customer')
        and exists(select 1 from public.bookings where id=v_reused.booking_id and venue_id is null and delivery_method='customer_pickup'
            and primary_customer_id<>v_customer),'archived customer excluded and pickup mapped');
end $$;

-- Inject a late failure after customer, venue, booking, and contact writes.
create function pg_temp.fail_pipeline_insert() returns trigger language plpgsql as $$
begin
    if new.submitted_data->'answers'->>'customer_name' = 'FAIL_PIPELINE_FIXTURE' then
        raise exception 'Injected fixture failure.' using errcode='P5199';
    end if;
    return new;
end $$;
create trigger test_pipeline_failure before insert on public.intake_submissions
for each row execute function pg_temp.fail_pipeline_insert();
set local role authenticated;
do $$
declare v_before bigint[]; v_after bigint[]; v_snapshot jsonb; v_request uuid := gen_random_uuid(); v_result record;
begin
    select array[(select count(*) from public.customers),(select count(*) from public.customer_identities),
        (select count(*) from public.venues),(select count(*) from public.bookings),(select count(*) from public.booking_contacts),
        (select count(*) from public.intake_submissions)] into v_before;
    v_snapshot := jsonb_set(pg_temp.answers(gen_random_uuid()::text || '@example.invalid'),'{answers,customer_name}','"FAIL_PIPELINE_FIXTURE"');
    v_snapshot := jsonb_set(v_snapshot,'{answers,facebook_identity}',to_jsonb(gen_random_uuid()::text));
    v_snapshot := jsonb_set(v_snapshot,'{answers,venue}','{"name":"Rollback","address_line_1":null,"address_line_2":null,"city":null,"state":null,"postal_code":null}');
    perform pg_temp.expect_error(format('select * from public.create_staff_inquiry(%L,%L::jsonb)',v_request,v_snapshot),'P5199');
    select array[(select count(*) from public.customers),(select count(*) from public.customer_identities),
        (select count(*) from public.venues),(select count(*) from public.bookings),(select count(*) from public.booking_contacts),
        (select count(*) from public.intake_submissions)] into v_after;
    perform pg_temp.check_true(v_before=v_after,'late failure rolls back every table');
    -- A failed transaction never consumes its request key.
    v_snapshot := jsonb_set(v_snapshot,'{answers,customer_name}','"Recovered"');
    select * into v_result from public.create_staff_inquiry(v_request,v_snapshot);
    perform pg_temp.check_true(not v_result.replayed,'retry after definite rollback');
end $$;
reset role;

-- Real role-based denials, not merely metadata checks.
set local role authenticated;
select pg_temp.expect_error('select * from inquiry_private.submit_inquiry(gen_random_uuid(),''{}'',''public_form'',null)','42501');
reset role;
set local request.jwt.claim.sub = '';
set local role authenticated;
select pg_temp.expect_error('select * from public.create_staff_inquiry(gen_random_uuid(),''{}'')','42501');
reset role;
set local role anon;
select pg_temp.expect_error('select * from public.create_staff_inquiry(gen_random_uuid(),''{}'')','42501');
select pg_temp.expect_error('select * from public.append_staff_inquiry_submission(gen_random_uuid(),gen_random_uuid(),''{}'')','42501');
select pg_temp.expect_error('select * from inquiry_private.submit_inquiry(gen_random_uuid(),''{}'',''public_form'',null)','42501');
select pg_temp.check_true(not exists(select 1 from public.bookings),'anonymous cannot read bookings');
select pg_temp.check_true(not exists(select 1 from public.intake_submissions),'anonymous cannot read submissions');
select pg_temp.expect_error('insert into public.intake_submissions(booking_id,submitted_data) values(gen_random_uuid(),''{}'')','42501');
reset role;
select 'Phase 5.3 isolated integration checks passed; fixtures will be rolled back.' as result;
rollback;
