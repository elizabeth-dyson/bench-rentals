-- TEST ONLY, disposable project, owner. Run after BOTH sessions finish each case.
do $$
declare f record; a record; b record; v_count integer;
begin
    select * into strict f from public_inquiry_test.fixture;
    select * into strict a from public_inquiry_test.results where scenario=f.scenario and participant='A';
    select * into strict b from public_inquiry_test.results where scenario=f.scenario and participant='B';
    if a.error_state is not null or a.replayed is distinct from false then raise exception 'A did not create one inquiry'; end if;
    if b.elapsed_seconds < 2 then raise exception 'No measured overlap; concurrency NOT verified. Repeat in a fresh test project.'; end if;
    if f.scenario='retry' then
        if b.replayed is distinct from true or b.error_state is not null or b.request_id <> a.request_id then
            raise exception 'Concurrent identical retry failed';
        end if;
    elsif b.error_state is distinct from 'P5401' then
        raise exception 'Concurrent budget enforcement failed';
    end if;
    select count(*) into v_count from public.intake_submissions where request_id in (a.request_id,b.request_id);
    if v_count <> 1 then raise exception 'Expected exactly one saved inquiry'; end if;
    if (select sum(used) from inquiry_private.public_rate_buckets) <> 3 then raise exception 'Wrong budget usage'; end if;
    raise notice 'PASS: % with measured lock overlap.',f.scenario;
end $$;
select scenario,participant,replayed,error_state,elapsed_seconds from public_inquiry_test.results order by scenario,participant;
-- After each verified pair run ONE of these, then A, B, and verification again:
-- select public_inquiry_test.prepare_case('session');
-- select public_inquiry_test.prepare_case('hour');
-- select public_inquiry_test.prepare_case('day');
