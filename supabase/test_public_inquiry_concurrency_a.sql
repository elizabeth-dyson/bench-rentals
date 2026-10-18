-- TEST ONLY, disposable project, owner. Run immediately before session B.
begin;
select public_inquiry_test.run_case('A');
commit;
