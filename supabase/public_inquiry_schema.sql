-- Phase 5.4 INSTALL 1/2. PENDING manual installation and isolated verification.
-- Inspect first. Requires installed 5.3. No customer rows are changed.
begin;
do $$ begin
    if to_regprocedure('inquiry_private.submit_inquiry(uuid,jsonb,text,uuid,uuid,jsonb)') is null then
        raise exception 'Install and verify Phase 5.3 first.';
    end if;
end $$;

create table if not exists inquiry_private.public_config (
    singleton boolean primary key default true check (singleton),
    enabled boolean not null default false,
    gateway_secret_hash text check (gateway_secret_hash ~ '^[0-9a-f]{64}$'),
    session_limit integer not null default 5 check (session_limit > 0),
    hourly_limit integer not null default 30 check (hourly_limit > 0),
    daily_limit integer not null default 100 check (daily_limit > 0)
);
insert into inquiry_private.public_config(singleton) values(true) on conflict do nothing;

-- Fixed UTC windows; session values are hashes of random server-generated UUIDs.
create table if not exists inquiry_private.public_rate_buckets (
    bucket_key text not null,
    starts_at timestamptz not null,
    expires_at timestamptz not null,
    used integer not null check (used > 0),
    primary key(bucket_key, starts_at),
    check (expires_at > starts_at)
);
create index if not exists public_rate_buckets_expiry on inquiry_private.public_rate_buckets(expires_at);
alter table inquiry_private.public_config enable row level security;
alter table inquiry_private.public_rate_buckets enable row level security;
revoke all on inquiry_private.public_config, inquiry_private.public_rate_buckets
    from public, anon, authenticated, service_role;
revoke all on schema inquiry_private from public, anon, authenticated, service_role;
commit;
