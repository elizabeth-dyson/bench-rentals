# Public inquiry form — Phase 5.4

**Status: code implemented locally; the user's post-installation inspection
confirms the Phase 5.4 SQL definitions in the inspected Supabase project.** The
new function body, owner, search path and grants match the installer; both new
private tables have the expected structure and permissions. Existing inspected
application tables, policies, triggers and function bodies are unchanged. Live
behavior and browser verification remain pending. The inspected project has not
been identified as production or a test project. The agent has not executed SQL
against Supabase or enabled public access.

This increment delivers the reusable initial form at `/inquiry` in the existing
Streamlit app. Private follow-up links (issuance, expiry, revocation and
resubmission) are explicitly deferred. Staff entry/review remains Phase 5.5.

## Behavior and boundaries

- Public requests bypass staff-cookie restoration and internal navigation, even
  when the browser also has an internal login. Internal routes keep their login
  requirement. The form uses a fresh anonymous client, never the staff client or
  a service-role key.
- Contact and event essentials come first. Venue, delivery preference, timing,
  referral source, rental notes and instructions are optional. Only name, event
  date, positive bench count and a usable preferred contact method are required.
  Past event dates and quantities above inventory remain valid inquiries.
- Requested timing is America/Chicago, with explicit repeated-hour selection and
  rejection of nonexistent DST times. It does not set inventory windows or
  confirm appointments.
- Review captures original answers; Submit verifies Turnstile, then atomically
  creates a lead and pending original submission through the Phase 5.3 operation.
  Matching and preservation rules remain in [INQUIRY_PIPELINE.md](INQUIRY_PIPELINE.md).
- Success reports receipt, not availability or confirmation. No email/text is
  sent. The lead appears in the existing internal workspace; review-specific
  labels and original-answer inspection remain Phase 5.5.
- Answers, request UUID and verification proof live in the open Streamlit session.
  Refreshing/closing the tab can lose them. After an uncertain response the form
  freezes the exact request and offers retry. It never silently changes UUIDs.
  A later authorization/throttle error does not resolve an earlier uncertain save.
  If the session is lost after an uncertain save, contact staff before resubmitting.

## Public service and SQL contract

`services/public_inquiry.py` contains pure public limits, Chicago wall-time
resolution, typed verification/receipt models and the explicit-client service:

```python
verify_public_inquiry(answers, *, request_id, token, verify) -> VerifiedInquiry
submit_public_inquiry(
    answers, *, request_id, session_id, verification, client, gateway_secret
) -> PublicInquiryReceipt
```

The UI generates random request/session UUIDs; neither is taken from URLs or
customer fields. Verification proof is server-only and binds the exact original
snapshot to the request UUID. It is reused only for that frozen logical request.
New/edited answers require new verification. Turnstile validation checks success,
expected hostname, and `initial_inquiry` action; the verification HTTP retry key
is stable for the same token/request and changes when the token is refreshed.
Tokens, secrets and customer payloads must not be logged.

```sql
public.create_public_inquiry(
    p_request_id uuid, p_snapshot jsonb,
    p_gateway_secret text, p_session_id uuid
) returns table(accepted boolean, request_id uuid, replayed boolean)
```

This narrow owner-owned SECURITY DEFINER wrapper has a fixed search path and
grants execution only to `anon` (and the installation owner). Execution alone
is insufficient: it verifies a server-held gateway secret against an owner-only
hash and checks the database enable flag on every call, including replays.
It never accepts booking targets, customer IDs, staff context or attribution.
It forces `public_form`, NULL actor/target and empty context when invoking 5.3.
No table grants, internal RLS policies or private-operation grants are broadened.
Keep `inquiry_private` out of PostgREST's exposed schemas.

The receipt contains only acceptance, the caller's request reference and replay
status. Customer matching and internal booking/submission IDs stay private.
Malformed/mismatched receipts and unrecognized RPC/transport errors are uncertain.

| SQLSTATE | Service outcome |
|---|---|
| `P5101` | `PublicValidationError` |
| `P5104` | `PublicConflictError` |
| `P5401` | `PublicThrottleError` |
| `42501` | `PublicAuthorizationError` |
| Other/transport/malformed receipt | `PublicInquiryError`: retain request and retry |

Turnstile errors raise `PublicVerificationError` before saving. User-facing
messages never include database exception text or configuration values.

## Limits and private metadata

Public limits are additional boundary limits; they do not constrain legacy/staff
workflows or rewrite existing records. Python and SQL enforce 200 characters for
names/event type/each venue field, 254 for email, 50 for phone, 500 for Facebook,
and 4,000 for each notes/instructions field. Serialized snapshots are capped at
65,536 UTF-8 bytes. Benches must fit a positive PostgreSQL integer. Existing
snapshot validation also rejects unknown keys and invalid types.

Two new owner-only, RLS-enabled tables in `inquiry_private` support public access:

- `public_config`: singleton, default-off enable flag, SHA-256 gateway hash, and
  positive configurable session/hour/day limits (defaults 5/30/100).
- `public_rate_buckets`: bucket key, start/expiry timestamps and usage count;
  unique key/start pair plus expiry index. Session keys hash random server UUIDs;
  no customer contact details or IPs are stored here.

Budgets use **fixed UTC windows**: five successful new inquiries per session per
15-minute window, 30 globally per hour and 100 globally per day. Adjacent windows
can each admit their own limit. New browser sessions can evade the session
budget, so Turnstile and global limits remain necessary. No IP is trusted as a
security identity. Global limits may temporarily block legitimate traffic during
an attack; staff can disable access or adjust the owner-only limits.

The request lock and configuration-row lock serialize retry/capacity decisions.
Identical completed retries bypass budget consumption after authorization.
Counters and business writes share one transaction; failed saves consume neither.
Expired buckets are pruned on the next valid new-save attempt; retained rows are
bounded by admissions and active windows. Missing configuration fails closed.

## SQL status and configuration

You ran the SQL in the inspected project and supplied matching inspection
reports. **Do not run either installer again just to follow this guide.** Use
the order below only for a fresh project or a deliberate reinstall. No Supabase
branch or second project is needed to use the current app.

1. **Inspect:** run the complete `supabase/inspect_inquiry_schema.sql` and save the
   full report. Compare with the installed 5.3 baseline and local definitions.
   Resolve drift first; `IF NOT EXISTS` does not validate an existing table.
2. **Install 1/2:** run the complete `supabase/public_inquiry_schema.sql`.
3. **Install 2/2:** run the complete `supabase/public_inquiry_rpc.sql`.
4. **Configure, leaving access disabled:** generate a new secret locally using
   `secrets.token_urlsafe(32)` and obtain its SHA-256 hexadecimal digest. Put the
   raw secret only in deployment secrets. Paste only its digest into SQL below:

   ```sql
   update inquiry_private.public_config
   set gateway_secret_hash = '<64 lowercase hexadecimal characters>',
       enabled = false, session_limit = 5, hourly_limit = 30, daily_limit = 100
   where singleton;
   ```

   A local Python example (run privately; do not share/commit its raw output):

   ```powershell
   uv run python -c "import secrets, hashlib; token = secrets.token_urlsafe(32); print('Deployment secret:', token); print('SQL hash:', hashlib.sha256(token.encode()).hexdigest())"
   ```

5. **Inspect again:** rerun the inspection script. Check the two private tables,
   their owners, constraints/indexes, RLS and denied API-role privileges; verify
   the wrapper owner, fixed search path and anon-only execute grant. Confirm
   application policies/grants and existing RPC bodies are unchanged. The report
   includes metadata only, never gateway hashes or counter contents.
6. **Behavior check:** use the rollback-only check below in the current project
   while public access is disabled, then perform the signed-out browser check.
   Record the pending two-session concurrency checks separately.

Both installers can be rerun in order without resetting configuration/counters.
Do not rerun older baseline installers alone; use the documented 5.3 order after
any baseline reinstall, followed by both 5.4 installers.

## Practical test path with one Supabase project

You do not need a paid Supabase branch or another Supabase project. The
`supabase/test_public_inquiry_rollback.sql` check is designed for the **current
project before sharing is enabled**. It uses a random `example.invalid` contact,
tests the anonymous create/retry/limit path, then rolls back its temporary
gateway setting, customer, booking, submission and rate counters. It does not
retain a test booking. Run the **entire file in one SQL Editor execution** as the
installation owner. Its first check requires the database `enabled` flag to be
false. Look for its final `PASS` notice and a successful `ROLLBACK`; if any
statement errors, run `ROLLBACK` and treat the check as failed. Do not run it
after real customers can submit: it temporarily locks the configuration row.
The inspection report does not include live configuration values, so check the
flag directly before running:

```sql
select enabled from inquiry_private.public_config where singleton;
```

The broader `supabase/test_public_inquiry.sql` also rolls back, but temporarily
adds a failure trigger on the submissions table. Leave that script for an
isolated environment. The following concurrency scripts **commit** synthetic
fixtures and modify settings, so **do not run them in the current customer
project**. Concurrency verification remains pending; it does not require you to
create another project before using the form. The single-transaction check and
real signed-out form smoke test give practical coverage of this deployment,
with the untested concurrent limit behavior stated honestly.

If a disposable database becomes available later, use the advanced checks:

1. Run `supabase/test_public_inquiry.sql` as owner. It rolls back its fixtures.
   Only a full successful run counts. On error issue `ROLLBACK`.
2. Run
   `supabase/test_public_inquiry_concurrency_setup.sql` once. This commits synthetic
   fixtures and a test-only gateway hash. Never use this project for customers.
3. Run `supabase/test_public_inquiry_concurrency_a.sql`, immediately followed by
   `supabase/test_public_inquiry_concurrency_b.sql` in another SQL Editor session.
   A holds locks for 15 seconds. Wait for both, then run
   `supabase/test_public_inquiry_concurrency_verify.sql`.
4. Repeat A → B → verify after **each** of these preparation calls, one at a time:

   ```sql
   select public_inquiry_test.prepare_case('session');
   -- Run A, B, verify before preparing the next case.
   select public_inquiry_test.prepare_case('hour');
   -- Run A, B, verify before preparing the next case.
   select public_inquiry_test.prepare_case('day');
   -- Run A, B, verify.
   ```

5. Require measured overlap in all four scenarios (retry/session/hour/day).
   No overlap is incomplete verification, not a pass. Avoid running near a
   quarter-hour boundary; the helper rejects starts within 30 seconds of it.
   Discard/reset the disposable project afterward; do not disable submission
   preservation to delete fixtures.

## Deployment secrets and activation

Configure the existing app with the following keys. These are placeholders, not
working credentials. Keep them in deployment secrets or ignored local secrets.

```toml
PUBLIC_INQUIRY_ENABLED = false
# Existing SUPABASE_URL is also used by the public form's anonymous client.
PUBLIC_SUPABASE_ANON_KEY = "<anon JWT or sb_publishable_ key; never service-role>"
PUBLIC_INQUIRY_GATEWAY_SECRET = "<generated token_urlsafe(32)>"
TURNSTILE_SITE_KEY = "<public site key>"
TURNSTILE_SECRET_KEY = "<private verification secret>"
PUBLIC_INQUIRY_HOSTNAME = "<exact deployed hostname, without scheme/path>"
# PUBLIC_INQUIRY_URL stays unset until the deployed signed-out flow is verified.
```

1. Configure a managed Turnstile widget for the deployed hostname. The UI uses
   action `initial_inquiry`. Use a real widget for the deployed hostname. Any
   test keys belong only in local test configuration.
2. Deploy the code after the rollback-only database check. The form stays
   unavailable while either application or database enable flag is off.
   Missing/invalid secrets also disable the form without exposing values.
3. To perform the real signed-out verification, set `PUBLIC_INQUIRY_ENABLED=true`
   and manually run:

   ```sql
   update inquiry_private.public_config set enabled=true where singleton;
   ```

4. Verify direct `/inquiry` access, real Turnstile, validation, saved receipt and
   staff-list visibility with one clearly labeled synthetic inquiry in the
   current project. This live form test creates a durable business record;
   retain it as history and mark it lost/cancelled through the normal workflow.
   Verify desktop/phone layouts, blocked/expired verification, and retry after an
   uncertain response. Also check an existing staff browser session on the public
   route and internal login/bookings regressions. Do not alter real customer records.
5. Set `PUBLIC_INQUIRY_URL="https://<deployed-host>/inquiry"` only after signed-out
   verification. Verify both Home and Bookings copy controls, actual clipboard
   contents, and manual-copy fallback on phone and desktop.

**Disable access:** first run
`update inquiry_private.public_config set enabled=false where singleton;`, then
set `PUBLIC_INQUIRY_ENABLED=false` and remove/blank `PUBLIC_INQUIRY_URL`. Disabling
only the sharing URL does not disable the endpoint. In-flight transactions that
already acquired the configuration lock may finish before the disable commits.
Receipts already confirmed remain saved; disabled access also blocks RPC retries.

**Rotate the gateway:** disable database access, generate a new raw secret/digest,
replace the application secret and database hash, redeploy/restart, verify, then
re-enable. Never store a raw secret in SQL files, business_settings, logs or Git.

Watch sanitized application error counts, Cloudflare verification results and
private bucket usage for unexpected throttling. Do not log payloads, challenge
tokens or credentials. Limits can be changed by the owner in `public_config`;
there is no staff settings screen in this phase.

## Local verification

On 2026-10-11, all **142 Python tests passed**, including 17 new public-inquiry
service/UI tests. The final `git diff --check` also passed.

New unit/AppTest coverage exercises public limits, DST, proof binding, safe
receipts/errors, disabled configuration, signed-out and signed-in public routing,
draft preservation, edit/review, success and identical uncertain retries. Run:

```powershell
uv run python -m unittest tests.test_public_inquiry tests.test_public_inquiry_page
uv run python -m unittest discover -s tests
```

SQL and procedural syntax were checked with a temporary pglast environment,
without a project dependency change. This does not execute SQL or verify RLS,
object resolution, transaction behavior or concurrency. No local PostgreSQL
runtime or connected browser was available; SQL integration, desktop/phone
layout, real Turnstile and clipboard verification remain pending.
