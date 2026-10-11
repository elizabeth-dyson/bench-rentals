-- READ ONLY. Run before/after installing Phase 5.1 or Phase 5.3.
-- Returns ONE result containing every inspection section, so copying the final
-- SQL Editor result includes the whole report. No customer rows or credentials.
with inspected_tables(table_name) as (
    values ('bookings'), ('customers'), ('customer_identities'),
           ('booking_contacts'), ('venues'), ('intake_links'), ('intake_submissions')
),
column_details as (
    select c.table_name, c.column_name, c.data_type, c.udt_schema, c.udt_name,
           c.is_nullable, c.column_default, c.ordinal_position
    from information_schema.columns c
    join inspected_tables t on t.table_name = c.table_name
    where c.table_schema = 'public'
),
constraint_details as (
    select c.relname as table_name, con.conname,
           pg_get_constraintdef(con.oid) as definition
    from pg_constraint con
    join pg_class c on c.oid = con.conrelid
    join pg_namespace n on n.oid = c.relnamespace
    join inspected_tables t on t.table_name = c.relname
    where n.nspname = 'public'
),
rls_details as (
    select c.relname as table_name, c.relrowsecurity as rls_enabled,
           c.relforcerowsecurity as rls_forced
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    join inspected_tables t on t.table_name = c.relname
    where n.nspname = 'public'
),
policy_details as (
    select p.*
    from pg_policies p
    join inspected_tables t on t.table_name = p.tablename
    where p.schemaname = 'public'
),
grant_details as (
    select g.table_name, g.grantee, g.privilege_type
    from information_schema.role_table_grants g
    join inspected_tables t on t.table_name = g.table_name
    where g.table_schema = 'public'
),
trigger_details as (
    select c.relname as table_name, tr.tgname, tr.tgenabled,
           pg_get_triggerdef(tr.oid) as definition,
           pg_get_functiondef(tr.tgfoid) as function_definition
    from pg_trigger tr
    join pg_class c on c.oid = tr.tgrelid
    join pg_namespace n on n.oid = c.relnamespace
    join inspected_tables t on t.table_name = c.relname
    where not tr.tgisinternal and n.nspname = 'public'
),
rpc_details as (
    select p.oid::regprocedure::text as signature,
           pg_get_userbyid(p.proowner) as owner,
           p.prosecdef as security_definer, p.proacl as permissions, p.proconfig as settings,
           pg_get_functiondef(p.oid) as definition
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where (n.nspname = 'public' and p.proname in (
        'create_lead', 'update_lead', 'set_lead_disposition', 'protect_intake_submission',
        'create_staff_inquiry', 'append_staff_inquiry_submission'
    )) or n.nspname = 'inquiry_private'
),
schema_details as (
    select n.nspname as schema_name, pg_get_userbyid(n.nspowner) as owner, n.nspacl as permissions
    from pg_namespace n where n.nspname = 'inquiry_private'
),
index_details as (
    select i.schemaname, i.tablename, i.indexname, i.indexdef
    from pg_indexes i join inspected_tables t on t.table_name = i.tablename
    where i.schemaname = 'public'
)
select jsonb_pretty(jsonb_build_object(
    'private_schemas', coalesce((select jsonb_agg(to_jsonb(d)) from schema_details d), '[]'::jsonb),
    'indexes', coalesce((select jsonb_agg(to_jsonb(d) order by tablename, indexname) from index_details d), '[]'::jsonb),
    'columns', coalesce((select jsonb_agg(to_jsonb(d) order by table_name, ordinal_position)
                         from column_details d), '[]'::jsonb),
    'constraints', coalesce((select jsonb_agg(to_jsonb(d) order by table_name, conname)
                             from constraint_details d), '[]'::jsonb),
    'rls', coalesce((select jsonb_agg(to_jsonb(d) order by table_name)
                     from rls_details d), '[]'::jsonb),
    'policies', coalesce((select jsonb_agg(to_jsonb(d) order by tablename, policyname)
                          from policy_details d), '[]'::jsonb),
    'grants', coalesce((select jsonb_agg(to_jsonb(d) order by table_name, grantee, privilege_type)
                        from grant_details d), '[]'::jsonb),
    'triggers', coalesce((select jsonb_agg(to_jsonb(d) order by table_name, tgname)
                          from trigger_details d), '[]'::jsonb),
    'functions', coalesce((select jsonb_agg(to_jsonb(d) order by signature)
                           from rpc_details d), '[]'::jsonb)
)) as schema_inspection;
