-- TEST ONLY. Start in a SEPARATE owner SQL session while session A is running.
-- This session should wait on each scenario's lock. Run verification afterward.
begin;
select inquiry_pipeline_test.run_case('retry','B');
commit;
begin;
select inquiry_pipeline_test.run_case('matching','B');
commit;
begin;
select inquiry_pipeline_test.run_case('numbering','B');
commit;
begin;
select inquiry_pipeline_test.run_case('followup','B');
commit;
