-- TEST ONLY, disposable project, owner. Start while session A is sleeping.
begin;
select public_inquiry_test.run_case('B');
commit;
