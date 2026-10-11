-- TEST ONLY. Read-only verification after both sessions finish successfully.
-- If any scenario did not overlap, the run is INCOMPLETE, not a concurrency pass.
do $$
begin
    if (select count(*) from inquiry_pipeline_test.results) <> 8 then
        raise exception 'Incomplete: both sessions must finish all four cases.';
    end if;
    if exists(select 1 from inquiry_pipeline_test.results where session_name='B' and elapsed_seconds<1) then
        raise exception 'Incomplete: at least one case did not contend. Repeat in a fresh disposable test environment, starting B immediately after A.';
    end if;
    if (select count(distinct submission_id) from inquiry_pipeline_test.results where scenario='retry') <> 1
       or (select count(*) from inquiry_pipeline_test.results where scenario='retry' and replayed) <> 1 then
        raise exception 'Duplicate request did not return exactly one original and one replay.';
    end if;
    if (select count(distinct b.primary_customer_id) from inquiry_pipeline_test.results r
        join public.bookings b on b.id=r.booking_id where r.scenario='matching') <> 1
       or (select count(distinct booking_id) from inquiry_pipeline_test.results where scenario='matching') <> 2 then
        raise exception 'Overlapping matches did not reuse one customer for two distinct inquiries.';
    end if;
    if (select count(distinct booking_number) from inquiry_pipeline_test.results where scenario='numbering') <> 2 then
        raise exception 'Concurrent booking numbers collided.';
    end if;
    if (select array_agg(submission_number order by submission_number) from inquiry_pipeline_test.results where scenario='followup')
        is distinct from array[1,2] then
        raise exception 'Concurrent legacy follow-ups did not receive consecutive distinct versions.';
    end if;
    if (select count(*) from public.intake_submissions s join inquiry_pipeline_test.fixture f on f.shared_request=s.request_id) <> 1 then
        raise exception 'Duplicate request created extra submissions.';
    end if;
end $$;
select 'Concurrency checks passed. Discard/reset the disposable test project; do not delete protected snapshots.' as result;
select * from inquiry_pipeline_test.results order by scenario,session_name;
