-- TEST ONLY. After concurrency_setup, run as owner in SQL session A.
-- Immediately start concurrency_b in a SEPARATE session while this runs.
-- Separate transactions are intentional. Four 15-second lock holds (~60 sec).
begin;
select inquiry_pipeline_test.run_case('retry','A');
commit;
begin;
select inquiry_pipeline_test.run_case('matching','A');
commit;
begin;
select inquiry_pipeline_test.run_case('numbering','A');
commit;
begin;
select inquiry_pipeline_test.run_case('followup','A');
commit;
