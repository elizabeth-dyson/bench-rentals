# Shared inquiry model — Phase 5.1

**Deployment status:** implemented locally; the user installed all three SQL
files on 2026-09-28. Their complete post-installation report confirms the expected
columns, constraints, enabled triggers, and matching function bodies. Existing
RLS settings, policies, and table grants are unchanged. Database integration
tests and desktop/phone workflow checks remain pending. The user executes
Supabase SQL. See [DATABASE.md](DATABASE.md) for the installed schema.

## Shared Python contract

`services/inquiries.py` contains frozen `InquiryAnswers`, `VenueInput`, and
`StaffInquiryContext` dataclasses with no Streamlit or Supabase imports.
`validate_inquiry_input` returns validation messages; `normalize_inquiry` and
`snapshot_inquiry_answers` raise `ValueError` for invalid answers. They perform
no I/O. Existing lead validation reuses the contact/event rules.

Require name, event date, positive integer bench count, and usable contact
information consistent with the preferred contact method. Event type, referral
source, venue/address, delivery preference, all timing, and instructions are
optional. Past events and requests exceeding inventory remain valid inquiries.

`normalize_inquiry` returns a separate working copy. It trims text, lowercases
email, normalizes phone digits and Facebook matching text, and converts aware
timestamps to `America/Chicago`. Blank optional text becomes `None`, an entirely
blank venue becomes `None`, and missing referral source becomes `other`.
No state/address defaults are invented. A partially supplied venue is retained.

| Answer/context | Working destination |
|---|---|
| Customer name | `customers.preferred_name` |
| Email, phone, preferred contact method | Corresponding customer fields |
| Facebook identity | `customer_identities`, with existing matching rules |
| Event date/type, requested benches | Corresponding booking fields |
| `source` | `bookings.source`; omitted maps to `other` |
| Venue name/address components | `venues`; booking links through `venue_id` |
| `delivery_preference` | `delivery_method_for_preference`: `parent_delivery` / `customer_pickup` map directly; `unsure` maps to NULL |
| Delivery, setup deadline, event start, pickup, rehearsal | Existing corresponding booking timestamp fields |
| `timing_notes` | New nullable `bookings.timing_notes` |
| `rental_notes` | `bookings.customer_notes` |
| Delivery/pickup instructions | Corresponding booking instruction fields |
| Staff customer-wide context | `customers.notes`; editing remains deferred |
| Staff rental context | `bookings.internal_notes` |
| Entry origin | New `entry_method`; never inferred from referral source |

Unknown venues remain unlinked; partial venue rows are supported. Matching venues
and writing the full inquiry are Phase 5.3/5.5 work. This mapping is the contract
for that future pipeline, not an implemented multi-table writer. Existing
`third_party`/`other` delivery values remain untouched; new-answer validation
does not restrict older records or the existing lead editor.

Timing inputs must be timezone-aware datetimes; the event date remains a date.
UI adapters must resolve local dates/times in America/Chicago before calling
the model, including explicitly resolving repeated fall DST times. Nonexistent
spring DST times and naive timestamps are rejected. Pickup cannot precede
delivery when both exist; other missing timing fields are allowed. Requested
times do not establish inventory windows or confirm appointments.

## Original answer snapshot

Call `snapshot_inquiry_answers(original_answers)` before normalization:

```json
{
  "schema_version": 1,
  "answers": {
    "customer_name": "  Example Customer  ",
    "event_date": "2027-06-14",
    "requested_bench_count": 12,
    "preferred_contact_method": "email",
    "email": " EXAMPLE@example.com ",
    "source": null
  }
}
```

This example is abbreviated: the serializer includes every `InquiryAnswers`
field, with absent optional values represented as null and the default delivery
preference as `unsure`. Venue fields form a nested object (or null). Dates use
ISO dates; timestamps use ISO 8601 with their supplied UTC offset. Text,
whitespace, supplied timestamp offsets, and missing source are preserved.
Snapshot original answers, never the normalized working copy.

Only fields declared on `InquiryAnswers` and `VenueInput` are serialized.
Staff notes, selected customer IDs, entry method, staff identity, and workflow
fields are excluded. Submission provenance belongs in separate database columns.
The future submission boundary must derive origin/staff attribution from its
trusted execution context, not accept them as customer answers.

Do not reconstruct historical snapshots from current working records. Existing
create/edit RPCs still do not create intake submissions; atomic creation and
retry protection remain Phase 5.3.

## Schema and compatibility

`supabase/inquiry_model.sql` adds nullable `bookings.entry_method` and
`bookings.timing_notes`, plus nullable `intake_submissions.entry_method` and
`submitted_by` UUID. The new immutable attribution field has no Auth foreign key,
so deleting an Auth user cannot clear historical submission attribution. Existing
booking creation and review attribution fields do reference Auth users.
Non-null origin is constrained to `public_form` or
`staff_entered`: public submissions have no staff attribution, staff submissions
require it, and legacy/unknown submissions retain both NULL.

Venue `address_line_1`, `city`, `state`, and `postal_code` become nullable and
the `state = 'NE'` default is removed. Existing address values are unchanged.
Submission `booking_id` remains required, with the existing unique
`(booking_id, submission_number)` constraint.

A BEFORE UPDATE/DELETE trigger protects ID, booking/link association, submission
number, original answers, submitted timestamp, entry method, and staff attribution.
Actual changes fail with SQLSTATE `23514`; no-op assignments and review metadata
updates remain valid. A BEFORE TRUNCATE trigger protects that removal path too.
These rules cover direct authenticated writes and RPCs. Existing rows are not
rewritten; unknown origins are not backfilled and historical notes are retained.

`customers.notes` means customer-wide staff context; `bookings.customer_notes`
means rental-specific requests; `bookings.internal_notes` means staff-only rental
context. The current UI labels the booking field **Rental notes**. Creating or
editing a lead no longer copies it into customer notes in the installed revised
RPC definitions. Customer-wide note editing remains deferred.

Python service functions now require `create_lead(lead, *, client)` and
`update_lead(lead, *, client)`; the UI supplies the authenticated session client.
SQL RPC names, parameters, return shapes, and booking numbering remain unchanged.
Creation records `staff_entered`; editing preserves origin. Later full inquiry
operations must likewise receive an explicit client/dependency.

## Installation and verification

1. Run `supabase/inspect_inquiry_schema.sql` in the target project's SQL Editor.
   It returns one `schema_inspection` JSON report containing every section; copy
   the entire report when sharing results. Earlier versions returned multiple
   result sets, so copying only the final result omitted table metadata.
   It reads columns/defaults, constraints, RLS policies, grants, triggers, and
   installed RPC definitions without reading customer rows. Compare with the
   baseline and pending changes. Resolve discrepancies before applying DDL;
   `IF NOT EXISTS` does not verify existing types or constraint definitions.
   Check for existing triggers that conflict with submission immutability.
2. First use an isolated Supabase test project with the verified baseline schema,
   RLS, and RPCs. Install `supabase/inquiry_model.sql`, then
   `supabase/create_lead_rpc.sql`, then `supabase/update_lead_rpc.sql`.
   Re-running this sequence is supported.
3. Run `supabase/test_inquiry_model.sql` in the isolated project's SQL Editor as
   owner. First create a synthetic Auth user in that isolated environment and
   replace the fixture UUID in the script's `request.jwt.claim.sub` setting with
   its ID. The inspected `bookings.created_by` and submission `reviewed_by` foreign
   keys require this Auth row; the script checks it before creating business
   fixtures. Never use real customer records as fixtures.
4. The integration script uses synthetic records, authenticated/anonymous roles,
   intentional write failures, and a final ROLLBACK. It checks new/reused
   customers, note separation/clearing, stable identifiers/origin, partial venues,
   invalid origin/attribution, submission uniqueness, immutable originals,
   permitted review updates, atomic failure recovery, and anonymous restrictions.
   If an error occurs, issue ROLLBACK immediately. With psql use
   `ON_ERROR_STOP=1`; only a successful complete run is verification.
5. After test verification, install the same three files in production before
   deploying dependent app changes. Installers do not create or edit business
   records. Do not run the fixture script in production.
6. Repeat the read-only inspection. Confirm added types/constraints, nullable
   venue components and removed state default, both protection triggers,
   `booking_id` still NOT NULL, unchanged RLS, and no anonymous RPC grants.
   Confirm create/update definitions implement note separation and staff origin.
   Record the installation/verification date in DATABASE.md.

**Current SQL verification:** the integration script has not been executed
against a database. Mocked RPC tests cannot establish SQL, transaction, or RLS
correctness. Run Python regression coverage with
`uv run python -m unittest discover -s tests`.

On 2026-09-28 the user supplied both pre- and post-installation reports. The
post-installation report contains seven tables, 103 columns, 35 constraints,
seven authenticated-only RLS policies, two enabled preservation triggers, and
four SECURITY INVOKER functions. All function bodies match the local SQL files;
lead create/update definitions no longer write customer-wide notes and creation
sets `staff_entered`. Both origin constraints and the attribution constraint are
installed. Venue address columns are nullable with no state default; submission
booking IDs remain required and submission-number uniqueness is unchanged.
RLS settings, policies, and table grants are identical to the baseline, with no
anonymous RPC execution grants. This confirms installation, not a behavioral
integration test run. Auth foreign keys require a synthetic Auth user for the
separate isolated integration script.
