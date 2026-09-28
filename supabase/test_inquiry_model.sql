-- INTEGRATION TEST: run ONLY on an isolated Supabase test project after installing
-- inquiry_model.sql, create_lead_rpc.sql, and update_lead_rpc.sql.
-- Requires the SQL Editor owner role (or psql owner with ON_ERROR_STOP=1).
-- First create a synthetic Auth user in that isolated project. Replace the UUID
-- below with its actual ID: bookings.created_by and submissions.reviewed_by
-- reference auth.users in the inspected live baseline.
-- All synthetic fixtures are rolled back. No pre-existing business rows are edited.
-- If a statement fails, explicitly ROLLBACK before doing anything else.
begin;
set local request.jwt.claim.sub = '00000000-0000-4000-8000-000000000051';
do $$
begin
    if not exists (select 1 from auth.users where id = auth.uid()) then
        raise exception 'Set request.jwt.claim.sub above to a synthetic Auth user UUID from this isolated test project before running the checks.';
    end if;
end;
$$;
set local role authenticated;

do $$
declare
    v_customer uuid;
    v_booking uuid;
    v_other_booking uuid;
    v_number text;
    v_other_number text;
    v_venue uuid;
    v_submission uuid;
    v_email text := gen_random_uuid()::text || '@example.invalid';
    v_original jsonb := '{"schema_version":1,"answers":{"customer_name":"  Fixture  ","source":null}}';
    v_column text;
    v_expression text;
begin
    insert into public.customers(preferred_name, email, preferred_contact_method, notes)
    values ('Inquiry fixture', v_email, 'email', 'Customer-wide fixture note') returning id into v_customer;

    select booking_id, booking_number into v_booking, v_number
    from public.create_lead(
        'Inquiry fixture', '2099-06-14', 12, 'email', 'other', v_email, null, null,
        null, null, 'Rental fixture note', 'Private fixture note', v_customer
    );
    if not exists (select 1 from public.bookings where id = v_booking and stage = 'lead'
                   and entry_method = 'staff_entered' and customer_notes = 'Rental fixture note'
                   and internal_notes = 'Private fixture note') then
        raise exception 'Creation did not preserve separate notes/origin/stage';
    end if;
    if (select notes from public.customers where id = v_customer) is distinct from 'Customer-wide fixture note' then
        raise exception 'Creation overwrote customer-wide notes';
    end if;
    if exists (select 1 from public.intake_submissions where booking_id = v_booking) then
        raise exception 'Legacy lead creation must not manufacture snapshots';
    end if;

    -- Also cover the new-customer branch of the existing creation RPC.
    select booking_id, booking_number into v_other_booking, v_other_number
    from public.create_lead(
        'Second fixture', '2099-06-15', 1, 'email', 'other',
        gen_random_uuid()::text || '@example.invalid', null, null,
        null, null, 'Second rental note', null, null
    );
    if exists (select 1 from public.bookings b join public.customers c on c.id = b.primary_customer_id
               where b.id = v_other_booking and c.notes is not null) then
        raise exception 'New customer inherited rental notes';
    end if;

    perform public.update_lead(v_number, 'Inquiry fixture', '2099-06-16', 10,
        'email', 'word_of_mouth', v_email, null, null, null, null, 'Revised rental', 'Revised private');
    if not exists (select 1 from public.bookings where id = v_booking and booking_number = v_number
                   and entry_method = 'staff_entered' and source = 'word_of_mouth'
                   and customer_notes = 'Revised rental' and internal_notes = 'Revised private') then
        raise exception 'Update changed identifiers/origin or failed to update rental notes';
    end if;
    if (select notes from public.customers where id = v_customer) is distinct from 'Customer-wide fixture note' then
        raise exception 'Update overwrote customer-wide notes';
    end if;
    perform public.update_lead(v_number, 'Inquiry fixture', '2099-06-16', 10,
        'email', 'other', v_email, null, null, null, null, '', '');
    if exists (select 1 from public.bookings where id = v_booking
               and (customer_notes is not null or internal_notes is not null))
       or (select notes from public.customers where id = v_customer) is distinct from 'Customer-wide fixture note' then
        raise exception 'Clearing rental notes affected customer notes or failed';
    end if;

    insert into public.venues(name, city) values ('Partial fixture venue', 'Lincoln') returning id into v_venue;
    if exists (select 1 from public.venues where id = v_venue and
               (state is not null or address_line_1 is not null or postal_code is not null)) then
        raise exception 'Partial venue acquired invented address defaults';
    end if;
    update public.bookings set venue_id = v_venue, timing_notes = 'Time to be clarified' where id = v_booking;
    begin
        update public.bookings set entry_method = 'facebook' where id = v_booking;
        raise exception 'Invalid booking origin was accepted';
    exception when check_violation then null;
    end;

    insert into public.intake_submissions(booking_id, submitted_data, entry_method, submitted_by)
    values (v_booking, v_original, 'staff_entered', auth.uid()) returning id into v_submission;
    insert into public.intake_submissions(booking_id, submission_number, submitted_data, entry_method)
    values (v_booking, 2, v_original, 'public_form');
    -- Legacy/unknown provenance remains readable without being guessed/backfilled.
    insert into public.intake_submissions(booking_id, submission_number, submitted_data)
    values (v_booking, 3, v_original);
    for v_expression in select unnest(array[
        '''invalid'', null', '''public_form'', auth.uid()',
        '''staff_entered'', null', 'null, auth.uid()'
    ]) loop
        begin
            execute format('insert into public.intake_submissions(booking_id, submission_number, submitted_data, entry_method, submitted_by) values (%L, 4, %L::jsonb, %s)',
                           v_booking, v_original, v_expression);
            raise exception 'Invalid submission provenance was accepted: %', v_expression;
        exception when check_violation then null;
        end;
    end loop;
    begin
        insert into public.intake_submissions(booking_id, submitted_data)
        values (v_booking, v_original);
        raise exception 'Duplicate submission number was accepted';
    exception when unique_violation then null;
    end;

    for v_column, v_expression in select * from (values
        ('id', 'gen_random_uuid()'),
        ('booking_id', quote_literal(v_other_booking) || '::uuid'),
        ('intake_link_id', 'gen_random_uuid()'),
        ('submission_number', '99'),
        ('submitted_data', '''{}''::jsonb'),
        ('submitted_at', 'now() + interval ''1 second'''),
        ('entry_method', '''public_form'''),
        ('submitted_by', 'gen_random_uuid()')
    ) as changes(column_name, expression) loop
        begin
            execute format('update public.intake_submissions set %I = %s where id = %L',
                           v_column, v_expression, v_submission);
            raise exception 'Protected submission field changed: %', v_column;
        exception when check_violation then null;
        end;
    end loop;
    begin
        delete from public.intake_submissions where id = v_submission;
        raise exception 'Submission deletion was accepted';
    exception when check_violation then null;
    end;
    begin
        -- BEFORE TRUNCATE must protect snapshots even if role has TRUNCATE grant.
        truncate public.intake_submissions;
        raise exception 'Submission truncation was accepted';
    exception when check_violation or insufficient_privilege then null;
    end;

    update public.intake_submissions set review_status = 'accepted', reviewed_by = auth.uid(),
        reviewed_at = now(), review_notes = 'Fixture review' where id = v_submission;
    perform public.update_lead(v_number, 'Inquiry fixture', '2099-06-16', 10,
        'email', 'other', v_email, null, null, null, null, 'Edited after intake', null);
    if not exists (select 1 from public.intake_submissions where id = v_submission
                   and submitted_data = v_original and review_status = 'accepted'
                   and review_notes = 'Fixture review') then
        raise exception 'Review or working-record edit rewrote original answers';
    end if;

    -- Force failure AFTER RPC customer writes, inside the same statement.
    -- A test-only trigger below protects real data by targeting only this fixture.
    perform set_config('bench_test.fail_customer', v_customer::text, true);
    perform set_config('bench_test.fixture_booking', v_booking::text, true);
end;
$$;

reset role;
create function public.phase51_test_reject_booking() returns trigger language plpgsql as $$
begin
    if new.primary_customer_id::text = current_setting('bench_test.fail_customer', true) then
        raise exception 'Synthetic booking write failure' using errcode = '23514';
    end if;
    return new;
end;
$$;
create trigger phase51_test_reject_booking before insert or update on public.bookings
for each row execute function public.phase51_test_reject_booking();
set local role authenticated;

do $$
declare
    v_customer uuid := current_setting('bench_test.fail_customer')::uuid;
    v_email text;
    v_number text;
    v_count bigint;
begin
    select email into v_email from public.customers where id = v_customer;
    select booking_number into v_number from public.bookings where primary_customer_id = v_customer;
    select count(*) into v_count from public.bookings;
    begin
        perform public.create_lead('Must roll back', '2099-06-16', 10, 'email', 'other',
            v_email, null, null, null, null, 'Failed rental', null, v_customer);
        raise exception 'Expected failed creation';
    exception when check_violation then null;
    end;
    begin
        perform public.update_lead(v_number, 'Must roll back', '2099-06-16', 10,
            'email', 'other', v_email, null, null, null, null, 'Failed rental', null);
        raise exception 'Expected failed update';
    exception when check_violation then null;
    end;
    if (select preferred_name from public.customers where id = v_customer) <> 'Inquiry fixture'
       or (select count(*) from public.bookings) <> v_count
       or (select customer_notes from public.bookings where booking_number = v_number) <> 'Edited after intake' then
        raise exception 'Failed writes left partial records';
    end if;
end;
$$;

reset role;
set local request.jwt.claim.sub = '';
set local role anon;
do $$
declare
    v_table text;
    v_count bigint;
    v_statement text;
begin
    foreach v_table in array array['bookings', 'customers', 'venues', 'intake_submissions'] loop
        begin
            execute format('select count(*) from public.%I', v_table) into v_count;
            if v_count <> 0 then raise exception 'Anonymous read exposed %', v_table; end if;
        exception when insufficient_privilege then null;
        end;
    end loop;
    foreach v_statement in array array[
        'insert into public.venues(name) values (''Anonymous fixture'')',
        'insert into public.customers(preferred_name) values (''Anonymous fixture'')',
        'insert into public.bookings(booking_number, event_date, requested_bench_count) values (gen_random_uuid()::text, ''2099-06-14'', 1)',
        format('insert into public.intake_submissions(booking_id, submission_number, submitted_data, entry_method) values (%L, 999, ''{}''::jsonb, ''public_form'')',
               current_setting('bench_test.fixture_booking'))
    ] loop
        begin
            execute v_statement;
            raise exception 'Anonymous insert was accepted: %', v_statement;
        exception when insufficient_privilege then null;
        end;
    end loop;
    if has_function_privilege('anon', 'public.create_lead(text,date,integer,text,text,text,text,text,text,text,text,text,uuid)', 'EXECUTE')
       or has_function_privilege('anon', 'public.update_lead(text,text,date,integer,text,text,text,text,text,text,text,text,text)', 'EXECUTE') then
        raise exception 'Anonymous callers have lead RPC execution permission';
    end if;
end;
$$;
reset role;
rollback;
select 'Phase 5.1 integration checks passed; all fixtures rolled back' as result;
