# Inquiry persistence — Phase 5.3

**Status:** implemented locally; the user installed both SQL files, and their
post-installation inspection confirms the expected definitions and metadata in
the inspected project. The initial report matched the verified Phase 5.1 baseline.
Isolated behavioral and two-session concurrency tests remain pending. The report
does not identify whether the inspected project is production or a test project.
Mocked RPC tests and schema inspection do not verify transaction/access behavior.

The ending report contains 106 columns, 38 constraints, 20 indexes, two enabled
preservation triggers, ten functions, and the owner-only `inquiry_private` schema.
All seven new/revised function bodies match the local installers. Staff wrappers
grant execution only to authenticated and the owner; private functions grant only
the owner. Legacy RPC bodies, RLS settings, policies, and table grants match the
initial report. This verifies installation, not successful execution of the saves.

This phase adds backend operations only. Add lead still uses its existing RPC,
without creating snapshots. Public routes, private links, anonymous submission,
and abuse protection belong to 5.4; expanded staff entry and review belong to
5.5. Leave `PUBLIC_INQUIRY_URL` unset until the signed-out form is verified.

## Python and SQL contracts

`services/inquiry_submission.py` imports neither Streamlit nor initialized clients:

```python
create_inquiry(answers, *, request_id, client, staff_context=None)
append_inquiry_submission(booking_id, answers, *, request_id, client)
```

Both accept complete `InquiryAnswers`, an authenticated session-scoped client,
and a caller-generated UUID per logical submission. They return
`InquirySubmissionResult(booking_id, booking_number, submission_id,
submission_number, replayed)`: UUIDs are strings, the version is a positive
integer, and replayed is a boolean. There is no public service operation yet.

Initial staff context allows `existing_customer_id`, `internal_notes`, and
`facebook_conversation_url`. Customer-profile notes are rejected, including an
explicit empty string. Follow-ups accept no staff-editing context. The client
never supplies staff attribution or origin to these RPCs:

- `create_staff_inquiry(p_request_id uuid, p_snapshot jsonb, p_staff_context jsonb)`
- `append_staff_inquiry_submission(p_request_id uuid, p_booking_id uuid, p_snapshot jsonb)`

The snapshot is the complete version-1 contract in [INQUIRY_MODEL.md](INQUIRY_MODEL.md),
including every answer key and every venue key when a venue object is present.
Text and supplied timestamp offsets stay unchanged. SQL rejects unknown fields,
invalid types, partial snapshots, unsupported versions, missing preferred
contacts, invalid dates/times, and pickup before delivery. It derives working
values from original answers rather than accepting an independent working payload.
Counts must fit the existing PostgreSQL integer column. Timestamp strings use
ISO dates/times with seconds, optional microseconds, and `Z` or `±HH:MM` offsets.
Python resolves named-zone DST issues before serialization; fixed-offset wire
timestamps denote instants and do not retain the original timezone name.

| SQLSTATE | Python exception | Meaning |
|---|---|---|
| `P5101` | `InquiryValidationError` | Invalid answers/context |
| `P5102` | `InquiryUnavailableError` | Missing booking or unavailable selected customer |
| `P5103` | `InquiryClosedError` | New follow-up requires an open `lead` |
| `P5104` | `InquiryConflictError` | Request already used for different content/context |
| `42501` | `InquiryAuthorizationError` | Authentication/access denied |
| Other/transport/malformed receipt | `InquirySubmissionError` | Save uncertain; retain request and answers |

Adapter messages do not expose database error text or customer data. A transport
or malformed-response error does not prove the transaction failed.

## Persistence and matching

Initial creation atomically writes the customer (if necessary), Facebook identity
(only for a new customer), optional partial venue, booking, primary booking
contact, and original submission. The booking starts in `lead`; submission 1
starts `pending`. Unknown venues stay unlinked; supplied venues get no invented
state or address, and no shared venue is updated. Field mappings follow 5.1.

Customer-wide notes are never written. Rental notes go to the booking's
`customer_notes`; staff rental context goes to `internal_notes`. Requested timing
does not set inventory windows or appointments. Confirmation, pricing, and hold
fields retain existing defaults.

Number allocation uses the existing `booking-number-{year}` advisory lock and
`BR-{year}-{sequence}` format, scanning the same bookings as legacy creation.
The new allocator pads to at least three digits without truncating larger values.
The unchanged legacy RPC's fixed-width padding above 999 is a pre-existing limit
to resolve before reaching that volume. Historical IDs/numbers are unchanged.

Follow-ups lock the booking, require `stage='lead'`, and append
`max(submission_number)+1`. Working records and prior review statuses stay intact.
A legacy lead with no snapshot receives submission 1, without reconstructing
original creation answers or unknown origin. Restore lost/cancelled leads first.

Only active customers participate in automatic matching. Normalize email
case/whitespace, phone digits, and Facebook case/repeated whitespace using the
existing contact rules. Never match on customer name alone. Every supplied
contact must match exactly one customer, and all must identify the same customer.
An unmatched extra contact prevents reuse. No contacts matching creates a new
customer; partial, conflicting, or ambiguous matches create a separate customer
requiring staff review.

Explicit staff selection must identify an active customer. Automatic and explicit
reuse preserve the entire existing profile and identities; supplied new contact
details remain in the submission. This differs from the unchanged legacy Add lead
workflow, which still updates supplied profile details until its 5.5 migration.

Immutable `customer_match_outcome` records `new_customer`, `reused_exact`,
`selected_by_staff`, or `needs_review` for initial submissions. Follow-up/legacy
rows have NULL. It records the original decision, not subsequent review resolution.
Phase 5.5 will present uncertain matches; no merge/cleanup is performed here.
Public wrappers must not return match results or existing profile details.

Sorted normalized contact-key transaction locks serialize overlapping new-pipeline
matching. Under default READ COMMITTED isolation, queries after waiting see prior
committed customer creation. Existing manual/legacy customer writes do not take
these locks; no new contact uniqueness constraint is imposed on shared identities.
Different request keys may legitimately create separate inquiries for one customer.

## Retry lifecycle and preservation

- Generate a UUID once per logical submission. Retain it with exact answers and
  context through reruns, double clicks, and uncertain responses.
- SQL takes a request-key lock and computes SHA-256 over canonical JSONB containing
  original answers, operation, target booking, trusted origin/actor, and accepted
  context. Omitted optional context keys and explicit nulls are equivalent.
- Same key/content returns the original receipt without allocating records or
  versions. Completed replays precede stage checks, so later closure is safe.
- Different content, target, actor, or origin with the same key conflicts. Changed
  original text, including whitespace, counts as changed content.
- A definite rejection/rollback does not consume the key. An uncertain outcome
  requires retrying the original payload first. Do not generate a new key just
  because a response was lost. Resolve that outcome before submitting edits as
  a new logical request.
- `request_id` is unique; `request_fingerprint` is a paired 64-character hex
  value. Existing rows retain NULLs. The preservation trigger protects both fields
  and matching outcome in addition to existing original/provenance fields.
  Review metadata remains mutable.

The trusted internal CRUD model remains. Unique constraints and preservation
cover direct authenticated writes; cross-table atomicity and fingerprint
computation are provided by the RPC. Do not emulate it with separate table writes.

## Access boundary

Private functions live in `inquiry_private`. Schema/function permissions are
revoked from PUBLIC, anon, authenticated, and service_role. Only the two staff
RPCs are granted to authenticated. These narrow SECURITY DEFINER wrappers are
owned by the trusted installation owner, explicitly require `auth.uid()`, derive
origin/actor, and use fixed search paths and qualified application references.
There is no application service-role client. Keep the private schema out of
PostgREST's exposed schemas.

The private operation supports `public_form` with NULL actor for owner-controlled
tests and future wrappers. Public mode rejects staff context. Customer answers
never accept customer IDs or workflow fields. The operation is not anonymously
callable, and its internal receipt is not an approved public response contract.

Phase 5.4 must authorize public access, resolve private tokens before supplying
follow-up targets, and add link association, expiry/revocation/resubmission checks,
retry authority, minimal public receipts, and abuse controls. No links or public
grants are introduced here. Search-path/grant design follows PostgreSQL's
[SECURITY DEFINER guidance](https://www.postgresql.org/docs/18/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY).
Fingerprinting uses built-in [SHA-256](https://www.postgresql.org/docs/16/functions-binarystring.html),
without a new extension.

## Manual installation and verification

You run all Supabase SQL; no scripts have been remotely installed by the agent.
Installation in the inspected project is confirmed above. The procedure below
also applies to preparing an isolated test project or another deployment target.

1. **Inspect:** run `supabase/inspect_inquiry_schema.sql`. Compare its complete
   report with the installed 5.1 baseline. It now includes private schema ownership,
   grants, indexes, new RPC ownership/settings/bodies. Resolve drift first;
   `IF NOT EXISTS` does not verify existing definitions.
2. **Install in an isolated project with the 5.1 baseline:** run
   `supabase/inquiry_pipeline_schema.sql`, then `supabase/inquiry_pipeline_rpc.sql`,
   each as a complete file under the trusted owner. Both installers are
   transactional and support rerunning in that order.
3. **Isolated behavior tests:** create a synthetic Auth user and put its UUID into
   `supabase/test_inquiry_pipeline.sql`. Run the entire script as owner. Fixtures
   and injected triggers roll back. On error, issue ROLLBACK; with psql use
   ON_ERROR_STOP=1. Only a full successful run is verification.
4. **Concurrency, disposable project only:** run
   `supabase/test_inquiry_concurrency_setup.sql` with the synthetic Auth UUID.
   This commits fixtures. Start `supabase/test_inquiry_concurrency_a.sql` and
   immediately run `supabase/test_inquiry_concurrency_b.sql` in another SQL Editor
   session. A holds each case's locks for 15 seconds (~one minute total). After
   both finish, run `supabase/test_inquiry_concurrency_verify.sql`. Missing overlap
   means incomplete, not passed. Discard/reset the disposable project afterward;
   do not disable snapshot protection to delete fixtures.
5. **Production:** after isolated verification, repeat inspection and the same
   two installers in order. Never run test scripts in production. Install before
   deploying dependent screens; current screens do not call these new RPCs yet.
6. **Verify installation:** rerun inspection. Confirm the three nullable columns,
   unique request/pair/matching constraints, both enabled preservation triggers
   and extended protection body, trusted wrapper ownership/search paths,
   authenticated-only wrapper grants, denied private/anonymous execution,
   unchanged RLS/table grants, and unchanged legacy RPC bodies. Record installation
   and behavioral test results separately.

Do not rerun the older 5.1 installer alone after 5.3: it restores the earlier
preservation body. If reinstalling the baseline, apply both 5.3 files again before
allowing application writes.

Local verification on 2026-09-29: all **125 Python tests passed** using
`uv run python -m unittest discover -s tests`. New SQL statements and procedural
bodies also passed a temporary pglast syntax-parser check; this does not resolve
database objects or execute transactions/RLS. No dependency was added to the
project for that check. No new
screens are connected, so existing UI tests apply without new layout work. No
local PostgreSQL/psql or Docker runtime was found; database verification remains
pending the isolated Supabase runs above.
