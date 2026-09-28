# Bench Rental App Database Architecture

This document describes the current Supabase/PostgreSQL database architecture for the Bench Rental Manager application.

The purpose of this file is to give developers and coding agents a reliable reference for the existing schema before making application or database changes.

> **Important:** The database was initially created manually through the Supabase UI, with additional constraints and indexes added through the SQL editor. Treat the existing Supabase database as the source of truth if this document and the live schema ever disagree.

> **Phase 5.1 deployment status:** Shared inquiry code and SQL are implemented
> locally. The user installed all three SQL files; installation was verified from
> the full post-installation report on 2026-09-28. The columns, constraints,
> enabled triggers, and installed function definitions match the changes below.
> Database integration tests and desktop/phone workflow checks remain **pending**.
> See [Shared inquiry model](INQUIRY_MODEL.md) for the field
> mapping, snapshot contract, schema differences, installation order, and checks.

## Installed Phase 5.1 schema changes

The post-installation inspection covers seven tables, 103 columns, 35 constraints,
seven authenticated-only RLS policies, two enabled submission preservation
triggers, and four functions. All installed function bodies match the local SQL
files, including the unchanged disposition RPC. RLS settings, policies, and table
grants match the pre-installation report. Existing `bookings.created_by`, `intake_links.created_by`,
and `intake_submissions.reviewed_by` reference `auth.users(id)` with ON UPDATE
CASCADE and ON DELETE SET NULL; isolated tests must use a real synthetic Auth
user. Table grants include `anon`, but there is no anonymous row-access policy.
RLS does not govern TRUNCATE; the installed submission preservation trigger also
covers that operation. Existing grants are not changed by Phase 5.1.

- `bookings`: added nullable `entry_method` (`public_form` / `staff_entered`) and
  `timing_notes`. Existing origins remain NULL; the revised `create_lead` sets
  `staff_entered`. Referral `source` remains a separate field.
- `intake_submissions`: added nullable `entry_method` and `submitted_by` UUID.
  Public origin requires NULL attribution, staff origin requires attribution,
  and legacy/unknown origin retains both NULL. Keep `booking_id` required and
  the existing `(booking_id, submission_number)` unique constraint.
- `venues`: allow NULL address line 1, city, state, and postal code; removed the
  automatic `NE` state default. Existing values are preserved.
- Submission triggers prevent changes to original answers/provenance, deletion,
  and truncation. Review metadata remains editable. Direct authenticated writes
  are covered; no new anonymous grants or public endpoint are introduced.
- `customers.notes` is customer-wide staff context; `bookings.customer_notes`
  is rental-specific requests; `bookings.internal_notes` is staff rental context.
  Revised lead RPCs write rental notes only to the booking. Historical copied
  notes remain untouched. Working-record edits never rewrite original answers.

Installed on 2026-09-28 in this order: `supabase/inquiry_model.sql`,
`supabase/create_lead_rpc.sql`, then `supabase/update_lead_rpc.sql`.
This verifies installation metadata and definitions, not execution of the
isolated database integration tests or a live application smoke test.
The exact steps and expected results are in [the installation guide](INQUIRY_MODEL.md#installation-and-verification).

---

## General Conventions

### Database

- Backend: Supabase
- Database: PostgreSQL
- Application schema: `public`
- Authentication: Supabase Auth
- Internal authenticated users live in Supabase's built-in `auth.users` table.
- There is currently **no custom `users`, `app_users`, or `profiles` table**.

### Primary Keys

Most application tables use:

```text
id uuid primary key default gen_random_uuid()
```

### Timestamps

Use:

```text
timestamptz
```

rather than timezone-naive timestamps.

Typical audit fields are:

```text
created_at timestamptz not null default now()
updated_at timestamptz not null default now()
```

### Money

Money values use:

```text
numeric(10,2)
```

Do not use floating-point types for currency.

### RLS

Row Level Security is enabled on the public application tables.

Current internal policy is intentionally simple:

```text
Role: authenticated
Command: ALL
USING: true
WITH CHECK: true
```

Meaning:

- Anonymous requests do not have application-table access.
- Any authenticated internal user currently has full CRUD access.
- There are no Mom/Dad/admin roles.
- All three internal users are trusted equally.

This may be tightened later if customer-facing authenticated access is introduced.

---

# Tables

## `customers`

Stores people associated with rentals.

A customer may have multiple bookings and may have multiple alternate identities, such as a different Facebook or Venmo name.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `legal_name` | `text` | Nullable |
| `preferred_name` | `text` | Nullable |
| `email` | `text` | Nullable |
| `phone` | `text` | Nullable |
| `preferred_contact_method` | `text` | Nullable |
| `notes` | `text` | Nullable |
| `is_archived` | `boolean` | NOT NULL, default `false` |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `preferred_contact_method` Values

```text
facebook
text
phone
email
```

### Indexes

```text
customers(email)
customers(phone)
```

---

## `customer_identities`

Stores alternate names/accounts associated with a customer.

This exists because the same person may appear under different names across Facebook, contracts, Venmo, email, etc.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `customer_id` | `uuid` | NOT NULL, FK → `customers.id` |
| `identity_type` | `text` | NOT NULL |
| `display_value` | `text` | NOT NULL |
| `profile_url` | `text` | Nullable |
| `is_primary_for_type` | `boolean` | NOT NULL, default `false` |
| `notes` | `text` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `identity_type` Values

```text
facebook
venmo
email
phone
spouse
alternate_contact
other
```

### Indexes

```text
customer_identities(identity_type, display_value)
```

---

## `venues`

Stores reusable event venue information.

This allows recurring venues to retain delivery/access notes and potentially delivery-distance information.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `name` | `text` | Nullable |
| `address_line_1` | `text` | Nullable |
| `address_line_2` | `text` | Nullable |
| `city` | `text` | Nullable |
| `state` | `text` | Nullable, no default |
| `postal_code` | `text` | Nullable |
| `latitude` | `numeric(9,6)` | Nullable |
| `longitude` | `numeric(9,6)` | Nullable |
| `distance_miles` | `numeric(7,2)` | Nullable |
| `standard_delivery_fee` | `numeric(10,2)` | Nullable |
| `access_notes` | `text` | Nullable |
| `delivery_notes` | `text` | Nullable |
| `is_archived` | `boolean` | NOT NULL, default `false` |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

---

## `bookings`

Central table for the entire rental lifecycle.

A record may begin as a serious lead and eventually become a completed rental.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_number` | `text` | NOT NULL, UNIQUE |
| `primary_customer_id` | `uuid` | Nullable, FK → `customers.id` |
| `venue_id` | `uuid` | Nullable, FK → `venues.id` |
| `stage` | `text` | NOT NULL, default `'lead'` |
| `source` | `text` | NOT NULL, default `'facebook_marketplace'` |
| `entry_method` | `text` | Nullable; `public_form` or `staff_entered` |
| `event_type` | `text` | Nullable |
| `event_date` | `date` | NOT NULL |
| `requested_bench_count` | `integer` | NOT NULL |
| `confirmed_bench_count` | `integer` | Nullable |
| `inventory_out_at` | `timestamptz` | Nullable |
| `inventory_return_at` | `timestamptz` | Nullable |
| `delivery_at` | `timestamptz` | Nullable |
| `setup_complete_by` | `timestamptz` | Nullable |
| `event_start_at` | `timestamptz` | Nullable |
| `pickup_at` | `timestamptz` | Nullable |
| `rehearsal_at` | `timestamptz` | Nullable |
| `timing_notes` | `text` | Nullable |
| `has_rehearsal_use` | `boolean` | NOT NULL, default `false` |
| `is_overnight` | `boolean` | NOT NULL, default `false` |
| `delivery_method` | `text` | Nullable |
| `current_quote_id` | `uuid` | Nullable, FK → `quotes.id` |
| `current_contract_id` | `uuid` | Nullable, FK → `contracts.id` |
| `quoted_total` | `numeric(10,2)` | Nullable |
| `deposit_required` | `numeric(10,2)` | Nullable |
| `amount_paid` | `numeric(10,2)` | NOT NULL, default `0` |
| `balance_remaining` | `numeric(10,2)` | Nullable |
| `hold_expires_at` | `timestamptz` | Nullable |
| `facebook_conversation_url` | `text` | Nullable |
| `customer_notes` | `text` | Nullable |
| `internal_notes` | `text` | Nullable |
| `delivery_instructions` | `text` | Nullable |
| `pickup_instructions` | `text` | Nullable |
| `cancellation_reason` | `text` | Nullable |
| `lost_reason` | `text` | Nullable |
| `created_by` | `uuid` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `stage` Values

```text
lead
availability_confirmed
hold
intake_sent
intake_received
pricing_review
quote_sent
quote_accepted
awaiting_confirmation
confirmed
upcoming
delivered
picked_up
completed
cancelled
lost
```

### Suggested `source` Values

```text
facebook_marketplace
facebook_referral
word_of_mouth
repeat_customer
other
```

### Suggested `delivery_method` Values

```text
parent_delivery
customer_pickup
third_party
other
```

### Check Constraints

```text
requested_bench_count > 0
confirmed_bench_count > 0
quoted_total >= 0
deposit_required >= 0
amount_paid >= 0
balance_remaining >= 0
inventory_return_at > inventory_out_at
pickup_at >= delivery_at
```

PostgreSQL `CHECK` constraints naturally pass when the relevant nullable values are `NULL`.

### Indexes

```text
bookings(event_date)
bookings(stage)
bookings(inventory_out_at, inventory_return_at)
bookings(primary_customer_id)
bookings(venue_id)
```

---

## `booking_contacts`

Links additional customers/contacts to a booking.

Examples include the contract signer, secondary customer, venue contact, delivery contact, or Venmo payer.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_id` | `uuid` | NOT NULL, FK → `bookings.id` |
| `customer_id` | `uuid` | NOT NULL, FK → `customers.id` |
| `contact_role` | `text` | NOT NULL |
| `is_primary` | `boolean` | NOT NULL, default `false` |
| `notes` | `text` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `contact_role` Values

```text
contract_signer
primary_customer
secondary_customer
venue_contact
delivery_contact
venmo_payer
other
```

### Unique Constraint

```text
UNIQUE (booking_id, customer_id, contact_role)
```

---

## `inventory_blocks`

Represents benches unavailable for non-booking reasons.

Examples:

- Broken benches
- Repainting/maintenance
- Personal/family use
- Temporarily removed from service

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `quantity` | `integer` | NOT NULL |
| `start_at` | `timestamptz` | NOT NULL |
| `end_at` | `timestamptz` | Nullable |
| `reason` | `text` | NOT NULL |
| `notes` | `text` | Nullable |
| `is_active` | `boolean` | NOT NULL, default `true` |
| `created_by` | `uuid` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

### Check Constraints

```text
quantity > 0
end_at > start_at
```

---

## `holds`

Tracks temporary inventory reservations before a booking becomes confirmed.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_id` | `uuid` | NOT NULL, FK → `bookings.id` |
| `quantity` | `integer` | NOT NULL |
| `inventory_start_at` | `timestamptz` | NOT NULL |
| `inventory_end_at` | `timestamptz` | NOT NULL |
| `expires_at` | `timestamptz` | NOT NULL |
| `status` | `text` | NOT NULL, default `'active'` |
| `released_reason` | `text` | Nullable |
| `released_at` | `timestamptz` | Nullable |
| `created_by` | `uuid` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `status` Values

```text
active
expired
released
converted
```

### Check Constraints

```text
quantity > 0
inventory_end_at > inventory_start_at
expires_at > created_at
```

### Indexes

```text
holds(status, expires_at)
holds(inventory_start_at, inventory_end_at)
```

---

## `intake_links`

Stores secure links used to send a specific customer to their booking-information form.

The raw secret token should not be stored directly; store a hash.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_id` | `uuid` | NOT NULL, FK → `bookings.id` |
| `token_hash` | `text` | NOT NULL, UNIQUE |
| `expires_at` | `timestamptz` | NOT NULL |
| `first_opened_at` | `timestamptz` | Nullable |
| `submitted_at` | `timestamptz` | Nullable |
| `revoked_at` | `timestamptz` | Nullable |
| `allow_resubmission` | `boolean` | NOT NULL, default `false` |
| `created_by` | `uuid` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |

---

## `intake_submissions`

Preserves exactly what a customer submitted through an intake form.

This provides an audit trail even if normalized booking/customer fields are later changed.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_id` | `uuid` | NOT NULL, FK → `bookings.id` |
| `intake_link_id` | `uuid` | Nullable, FK → `intake_links.id` |
| `submission_number` | `integer` | NOT NULL, default `1` |
| `entry_method` | `text` | Nullable; `public_form` or `staff_entered` |
| `submitted_by` | `uuid` | Nullable; required for `staff_entered`, otherwise NULL; no Auth FK |
| `submitted_data` | `jsonb` | NOT NULL |
| `submitted_at` | `timestamptz` | NOT NULL, default `now()` |
| `review_status` | `text` | NOT NULL, default `'pending'` |
| `reviewed_by` | `uuid` | Nullable |
| `reviewed_at` | `timestamptz` | Nullable |
| `review_notes` | `text` | Nullable |

### Suggested `review_status` Values

```text
pending
accepted
needs_clarification
superseded
```

### Unique Constraint

```text
UNIQUE (booking_id, submission_number)
```

---

## `pricing_rules`

Stores configurable pricing logic.

Pricing should eventually be driven by data rather than hardcoding business prices throughout the Python application.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `rule_code` | `text` | NOT NULL |
| `name` | `text` | NOT NULL |
| `description` | `text` | Nullable |
| `rule_type` | `text` | NOT NULL |
| `calculation_method` | `text` | NOT NULL |
| `amount` | `numeric(10,2)` | Nullable |
| `percentage` | `numeric(7,4)` | Nullable |
| `configuration` | `jsonb` | NOT NULL, default `{}` |
| `effective_from` | `date` | NOT NULL |
| `effective_until` | `date` | Nullable |
| `priority` | `integer` | NOT NULL, default `100` |
| `is_active` | `boolean` | NOT NULL, default `true` |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `rule_type` Values

```text
bench_rate
minimum_rental
delivery_base
delivery_mileage
small_order_fee
rehearsal_fee
overnight_fee
additional_day
setup_fee
deposit
discount
custom
```

### Suggested `calculation_method` Values

```text
flat
per_bench
per_mile
percentage
tiered
minimum
manual
```

### Unique Constraint

```text
UNIQUE (rule_code, effective_from)
```

---

## `quotes`

Stores versioned quotes for bookings.

A booking may have multiple historical quotes, but only one should be treated as the current quote.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_id` | `uuid` | NOT NULL, FK → `bookings.id` |
| `version_number` | `integer` | NOT NULL |
| `status` | `text` | NOT NULL, default `'draft'` |
| `subtotal` | `numeric(10,2)` | NOT NULL, default `0` |
| `discount_total` | `numeric(10,2)` | NOT NULL, default `0` |
| `fee_total` | `numeric(10,2)` | NOT NULL, default `0` |
| `total` | `numeric(10,2)` | NOT NULL |
| `deposit_required` | `numeric(10,2)` | NOT NULL, default `0` |
| `balance_after_deposit` | `numeric(10,2)` | NOT NULL |
| `valid_until` | `timestamptz` | Nullable |
| `pricing_explanation` | `text` | Nullable |
| `internal_override_reason` | `text` | Nullable |
| `customer_message` | `text` | Nullable |
| `sent_at` | `timestamptz` | Nullable |
| `viewed_at` | `timestamptz` | Nullable |
| `accepted_at` | `timestamptz` | Nullable |
| `declined_at` | `timestamptz` | Nullable |
| `superseded_at` | `timestamptz` | Nullable |
| `created_by` | `uuid` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `status` Values

```text
draft
sent
viewed
accepted
declined
expired
superseded
```

### Check Constraints

```text
subtotal >= 0
discount_total >= 0
fee_total >= 0
total >= 0
deposit_required >= 0
balance_after_deposit >= 0
deposit_required <= total
balance_after_deposit = total - deposit_required
```

### Unique Constraint

```text
UNIQUE (booking_id, version_number)
```

### Indexes

```text
quotes(booking_id, status)
```

---

## `quote_items`

Stores individual pricing lines belonging to a quote.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `quote_id` | `uuid` | NOT NULL, FK → `quotes.id` |
| `pricing_rule_id` | `uuid` | Nullable, FK → `pricing_rules.id` |
| `item_type` | `text` | NOT NULL |
| `description` | `text` | NOT NULL |
| `quantity` | `numeric(10,2)` | NOT NULL, default `1` |
| `unit_price` | `numeric(10,2)` | NOT NULL |
| `amount` | `numeric(10,2)` | NOT NULL |
| `is_manual` | `boolean` | NOT NULL, default `false` |
| `calculation_details` | `jsonb` | NOT NULL, default `{}` |
| `sort_order` | `integer` | NOT NULL, default `100` |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `item_type` Values

```text
bench_rental
delivery
mileage
duration
rehearsal
overnight
setup
discount
surcharge
custom
```

---

## `contract_templates`

Stores versioned contract language/templates.

Existing template versions should not be overwritten after being used.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `name` | `text` | NOT NULL |
| `version_number` | `integer` | NOT NULL |
| `template_content` | `text` | NOT NULL |
| `effective_from` | `date` | NOT NULL |
| `effective_until` | `date` | Nullable |
| `is_active` | `boolean` | NOT NULL, default `true` |
| `created_by` | `uuid` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |

### Unique Constraint

```text
UNIQUE (name, version_number)
```

---

## `contracts`

Stores generated and electronically signed rental agreements.

Actual contract files will eventually live in private Supabase Storage.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_id` | `uuid` | NOT NULL, FK → `bookings.id` |
| `quote_id` | `uuid` | NOT NULL, FK → `quotes.id` |
| `template_id` | `uuid` | NOT NULL, FK → `contract_templates.id` |
| `version_number` | `integer` | NOT NULL |
| `status` | `text` | NOT NULL, default `'draft'` |
| `unsigned_file_path` | `text` | Nullable |
| `signed_file_path` | `text` | Nullable |
| `audit_file_path` | `text` | Nullable |
| `signature_provider` | `text` | Nullable |
| `provider_envelope_id` | `text` | Nullable |
| `signer_name` | `text` | Nullable |
| `signer_email` | `text` | Nullable |
| `generated_at` | `timestamptz` | Nullable |
| `sent_at` | `timestamptz` | Nullable |
| `viewed_at` | `timestamptz` | Nullable |
| `signed_at` | `timestamptz` | Nullable |
| `voided_at` | `timestamptz` | Nullable |
| `void_reason` | `text` | Nullable |
| `created_by` | `uuid` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `status` Values

```text
draft
generated
sent
viewed
signed
declined
voided
superseded
```

### Unique Constraint

```text
UNIQUE (booking_id, version_number)
```

### Indexes

```text
contracts(booking_id, status)
```

---

## `expected_payments`

Represents payments the system expects to receive.

Examples include deposits and final balances.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_id` | `uuid` | NOT NULL, FK → `bookings.id` |
| `payment_type` | `text` | NOT NULL |
| `expected_amount` | `numeric(10,2)` | NOT NULL |
| `due_at` | `timestamptz` | Nullable |
| `expected_payer_name` | `text` | Nullable |
| `expected_method` | `text` | Nullable |
| `status` | `text` | NOT NULL, default `'expected'` |
| `notes` | `text` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `payment_type` Values

```text
deposit
final_balance
additional_charge
damage_charge
refund
other
```

### Suggested `status` Values

```text
expected
verification_needed
partially_received
received
waived
cancelled
overdue
refunded
```

### Suggested Payment Methods

```text
venmo
cash
check
other
```

### Check Constraint

```text
expected_amount > 0
```

### Indexes

```text
expected_payments(booking_id, status)
expected_payments(due_at)
```

---

## `payments`

Stores actual financial transactions.

A payment may optionally correspond to an `expected_payments` record.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_id` | `uuid` | NOT NULL, FK → `bookings.id` |
| `expected_payment_id` | `uuid` | Nullable, FK → `expected_payments.id` |
| `transaction_direction` | `text` | NOT NULL, default `'received'` |
| `amount` | `numeric(10,2)` | NOT NULL |
| `method` | `text` | NOT NULL |
| `actual_payer_name` | `text` | Nullable |
| `venmo_note` | `text` | Nullable |
| `external_reference` | `text` | Nullable |
| `received_at` | `timestamptz` | NOT NULL |
| `verification_status` | `text` | NOT NULL, default `'verified'` |
| `verified_by` | `uuid` | Nullable |
| `verified_at` | `timestamptz` | Nullable |
| `screenshot_file_path` | `text` | Nullable |
| `notes` | `text` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `transaction_direction` Values

```text
received
refunded
```

### Suggested `verification_status` Values

```text
pending
verified
rejected
```

### Check Constraint

```text
amount > 0
```

### Indexes

```text
payments(booking_id)
payments(actual_payer_name)
```

---

## `booking_changes`

Stores meaningful booking changes.

Useful for tracking logistics changes that may arrive via Facebook, text, phone, email, or in person.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_id` | `uuid` | NOT NULL, FK → `bookings.id` |
| `change_category` | `text` | NOT NULL |
| `field_name` | `text` | NOT NULL |
| `old_value` | `text` | Nullable |
| `new_value` | `text` | Nullable |
| `source` | `text` | Nullable |
| `change_reason` | `text` | Nullable |
| `requires_contract_update` | `boolean` | NOT NULL, default `false` |
| `customer_notified` | `boolean` | NOT NULL, default `false` |
| `customer_notified_at` | `timestamptz` | Nullable |
| `changed_by` | `uuid` | Nullable |
| `changed_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `change_category` Values

```text
contact
venue
inventory
timing
pricing
payment
contract
status
other
```

### Suggested `source` Values

```text
facebook
text
phone
email
in_person
customer_form
internal
other
```

### Index

```text
booking_changes(booking_id, changed_at)
```

---

## `communications`

Tracks important communications related to a booking.

This table is not intended to replicate full Facebook/Text/Email histories.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_id` | `uuid` | NOT NULL, FK → `bookings.id` |
| `customer_id` | `uuid` | Nullable, FK → `customers.id` |
| `direction` | `text` | NOT NULL |
| `channel` | `text` | NOT NULL |
| `communication_type` | `text` | NOT NULL |
| `recipient_or_sender` | `text` | Nullable |
| `subject` | `text` | Nullable |
| `summary` | `text` | Nullable |
| `message_body` | `text` | Nullable |
| `external_message_id` | `text` | Nullable |
| `occurred_at` | `timestamptz` | NOT NULL, default `now()` |
| `recorded_by` | `uuid` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `direction` Values

```text
incoming
outgoing
internal
```

### Suggested `channel` Values

```text
facebook
text
phone
email
in_person
system
other
```

### Suggested `communication_type` Values

```text
availability_response
intake_sent
quote_sent
quote_reminder
contract_sent
contract_reminder
deposit_reminder
confirmation
delivery_reminder
change_confirmation
pickup_message
general
```

### Index

```text
communications(booking_id, occurred_at)
```

---

## `tasks`

Stores internal action items.

Examples:

- Follow up before a hold expires
- Review intake form
- Prepare quote
- Verify payment
- Follow up on unsigned contract
- Delivery/pickup tasks

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_id` | `uuid` | Nullable, FK → `bookings.id` |
| `task_type` | `text` | NOT NULL |
| `title` | `text` | NOT NULL |
| `description` | `text` | Nullable |
| `due_at` | `timestamptz` | Nullable |
| `priority` | `text` | NOT NULL, default `'normal'` |
| `status` | `text` | NOT NULL, default `'open'` |
| `assigned_to` | `uuid` | Nullable |
| `completed_at` | `timestamptz` | Nullable |
| `completed_by` | `uuid` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `task_type` Values

```text
follow_up
review_intake
prepare_quote
verify_payment
contract_follow_up
delivery
pickup
customer_change
other
```

### Suggested `priority` Values

```text
low
normal
high
urgent
```

### Suggested `status` Values

```text
open
in_progress
completed
cancelled
```

### Indexes

```text
tasks(status, due_at)
tasks(assigned_to, status)
```

---

## `documents`

General-purpose file registry.

Actual files should eventually live in Supabase Storage.

Examples:

- Venue maps
- Payment screenshots
- Damage photos
- Delivery photos
- Supplemental documents

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_id` | `uuid` | Nullable, FK → `bookings.id` |
| `customer_id` | `uuid` | Nullable, FK → `customers.id` |
| `document_type` | `text` | NOT NULL |
| `file_name` | `text` | NOT NULL |
| `storage_bucket` | `text` | NOT NULL |
| `storage_path` | `text` | NOT NULL |
| `mime_type` | `text` | Nullable |
| `file_size_bytes` | `bigint` | Nullable |
| `description` | `text` | Nullable |
| `uploaded_by` | `uuid` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `document_type` Values

```text
venue_map
payment_screenshot
damage_photo
customer_attachment
contract_attachment
delivery_photo
other
```

### Unique Constraint

```text
UNIQUE (storage_bucket, storage_path)
```

---

## `calendar_events`

Tracks application events synchronized with an external calendar provider.

Google Calendar is the intended initial provider.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `booking_id` | `uuid` | NOT NULL, FK → `bookings.id` |
| `event_type` | `text` | NOT NULL |
| `provider` | `text` | NOT NULL, default `'google'` |
| `external_calendar_id` | `text` | Nullable |
| `external_event_id` | `text` | Nullable |
| `starts_at` | `timestamptz` | NOT NULL |
| `ends_at` | `timestamptz` | Nullable |
| `sync_status` | `text` | NOT NULL, default `'pending'` |
| `last_synced_at` | `timestamptz` | Nullable |
| `last_sync_error` | `text` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

### Suggested `event_type` Values

```text
delivery
event
pickup
hold_expiration
payment_due
other
```

### Suggested `sync_status` Values

```text
pending
synced
failed
deleted
```

### Partial Unique Index

Provider + external event ID must be unique when an external event ID exists:

```sql
create unique index calendar_events_provider_external_event_unique
on public.calendar_events (provider, external_event_id)
where external_event_id is not null;
```

### Index

```text
calendar_events(booking_id)
```

---

## `business_settings`

Stores configurable application/business settings.

Do not store deployment credentials or API secrets here.

### Columns

| Column | Type | Nullability / Default |
|---|---|---|
| `id` | `uuid` | PK, NOT NULL, default UUID |
| `setting_key` | `text` | NOT NULL, UNIQUE |
| `value` | `jsonb` | NOT NULL |
| `description` | `text` | Nullable |
| `is_secret` | `boolean` | NOT NULL, default `false` |
| `updated_by` | `uuid` | Nullable |
| `created_at` | `timestamptz` | NOT NULL, default `now()` |
| `updated_at` | `timestamptz` | NOT NULL, default `now()` |

### Expected Future Settings

```text
business_name
total_bench_count
default_hold_hours
default_quote_valid_hours
default_state
home_base_address
service_radius_miles
business_email
mom_phone
venmo_username
venmo_phone_last_four
deposit_policy
booking_number_next_sequence
```

True secrets such as API keys belong in Streamlit/Supabase deployment secrets, not this table.

---

# High-Level Relationships

```text
auth.users
    └── internal authentication only

customers
    ├── customer_identities
    ├── booking_contacts
    └── bookings

venues
    └── bookings

bookings
    ├── booking_contacts
    ├── holds
    ├── intake_links
    ├── intake_submissions
    ├── quotes
    │   └── quote_items
    ├── contracts
    ├── expected_payments
    │   └── payments
    ├── booking_changes
    ├── communications
    ├── tasks
    ├── documents
    └── calendar_events

pricing_rules
    └── quote_items

contract_templates
    └── contracts
```

---

# Availability Model

The business currently owns approximately 22 interchangeable benches.

Availability should eventually account for:

1. Confirmed bookings whose inventory windows overlap the requested period.
2. Active temporary holds whose inventory windows overlap the requested period.
3. Active `inventory_blocks` representing unavailable benches.

The relevant booking inventory window is:

```text
inventory_out_at
→
inventory_return_at
```

This is intentionally separate from the event date because benches may be delivered before the event and picked up afterward.

---

# Booking Confirmation Rule

A booking is intended to become fully confirmed only after:

```text
signed contract received
AND
required deposit received/verified
```

The app will eventually automate this workflow.

---

# Authentication / Authorization Model

The application currently has three trusted internal users:

- Liz
- Mom
- Dad

There are intentionally no internal role distinctions.

Current model:

```text
Unauthenticated
    → no internal application access

Authenticated
    → full internal application access
```

Do not introduce admin/operations/payment roles unless this architecture is explicitly reconsidered later.

## Browser session restoration

The Streamlit app persists only the Supabase refresh token in a browser cookie so
an authenticated user can refresh or directly reopen an internal route without
signing in again. The cookie is same-site, becomes Secure on HTTPS, expires after
30 days, and is rotated through Supabase whenever a new Streamlit session is
restored. Logout revokes the Supabase session and removes the cookie. The app
still creates a separate Supabase client for each Streamlit session; authenticated
clients and access tokens are never cached globally.

---

# Customer Access

Customers will eventually receive private/tokenized links for workflows such as:

- Intake form
- Quote review
- Potentially contract/signing flow

Do not assume customers are Supabase Auth users.

Customer-facing access should be designed separately and narrowly so it does not weaken the internal authenticated RLS model.

---

# Delete / History Philosophy

The application should generally preserve historical business data.

Prefer:

```text
cancel
archive
void
supersede
release
```

over destructive deletion for meaningful booking, financial, quote, and contract records.

Historical versions are especially important for:

- Quotes
- Contracts
- Payments
- Customer submissions
- Booking changes

---

# Existing Explicit Indexes

In addition to indexes automatically created for primary keys and unique constraints, the schema includes:

```text
bookings(event_date)
bookings(stage)
bookings(inventory_out_at, inventory_return_at)
bookings(primary_customer_id)
bookings(venue_id)

holds(status, expires_at)
holds(inventory_start_at, inventory_end_at)

customers(email)
customers(phone)

customer_identities(identity_type, display_value)

quotes(booking_id, status)

contracts(booking_id, status)

expected_payments(booking_id, status)
expected_payments(due_at)

payments(booking_id)
payments(actual_payer_name)

tasks(status, due_at)
tasks(assigned_to, status)

calendar_events(booking_id)

communications(booking_id, occurred_at)

booking_changes(booking_id, changed_at)
```

---

# Important Development Rule

Before changing this schema:

1. Inspect this document.
2. Inspect the live Supabase schema if needed.
3. Determine whether the existing structure already supports the feature.
4. Avoid adding duplicate columns/tables for concepts that already exist.
5. If a schema change is genuinely needed, document why.
6. Update this file when the live database schema changes.

Do not redesign the database simply because a different structure might also work.

The existing schema is the baseline architecture for the project.

---

# Application RPCs

## `create_lead`

**Installed Phase 5.1 revision (2026-09-28):** requires `supabase/inquiry_model.sql`
first on a new database. It sets `bookings.entry_method = 'staff_entered'`
and writes rental notes only to `bookings.customer_notes`. It never writes or
clears `customers.notes`, including when reusing a customer. Its signature and
return shape remain unchanged; it does not yet create intake submissions.

Phase 4.3 adds an authenticated `SECURITY INVOKER` function that creates a lead
as one PostgreSQL transaction. It reuses or creates the customer, maintains the
Facebook identity, generates a `BR-{event year}-{sequence}` booking number,
creates the booking, and creates its primary `booking_contacts` relationship.

The function does not bypass RLS. Execution is revoked from `public` and `anon`
and granted only to `authenticated`.

### Installation

1. Open the Supabase dashboard for this project.
2. Open **SQL Editor** and create a new query.
3. Paste and run the complete contents of `supabase/create_lead_rpc.sql`.
4. Confirm the final verification query returns `create_lead`.

Running the installation SQL does not create a customer or booking. End-to-end
verification should be performed through the authenticated application after
installation so the transaction runs under the same RLS context as normal use.

## `update_lead`

**Installed Phase 5.1 revision (2026-09-28):** the current SQL writes rental notes only to
`bookings.customer_notes`. It preserves `customers.notes` and the booking's
original `entry_method`. The RPC signature remains unchanged.

Phase 4.5 adds an authenticated `SECURITY INVOKER` function that updates a
lead and its shared customer as one transaction. It validates that the booking
is still in the `lead` stage, protects against contact information belonging to
another customer, maintains the primary Facebook identity, and leaves the
booking number unchanged.

The function does not bypass RLS. Execution is revoked from `public` and `anon`
and granted only to `authenticated`.

### Installation

1. Open the Supabase dashboard for this project.
2. Open **SQL Editor** and create a new query.
3. Paste and run the complete contents of `supabase/update_lead_rpc.sql`.
4. Confirm the final verification query returns `update_lead`.

Running the installation SQL does not modify any customer or booking rows.

## `set_lead_disposition`

Phase 4.7 adds an authenticated `SECURITY INVOKER` function that atomically
marks an active lead as `lost` or `cancelled`, or restores a closed lead to
`lead`. The function locks the selected booking, requires a reason when closing
a lead, rejects stale or unsupported transitions, and keeps the lost and
cancellation reason fields mutually exclusive. Restoring a lead clears both
reason fields.

The function does not bypass RLS. Execution is revoked from `public` and `anon`
and granted only to `authenticated`. It does not write `booking_changes`;
formal booking-change history remains deferred to Phase 12.

### Installation

1. Open the Supabase dashboard for this project.
2. Open **SQL Editor** and create a new query.
3. Paste and run the complete contents of
   `supabase/set_lead_disposition_rpc.sql`.
4. Confirm the final verification query returns `set_lead_disposition`.

Running the installation SQL does not modify any booking rows. End-to-end
verification should be performed through the authenticated application after
installation so the transition runs under the same RLS context as normal use.
