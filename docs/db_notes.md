# Database Info

## `customers` Table

### `preferred_contact_method` Options:

- facebook
- text
- call
- email

## `customer_identities` Table

### `identity_type` Options

- facebook
- venmo
- email
- phone
- spouse
- alternate_contact
- other

## `bookings` Table

### `stage` Options:

- lead
- availability_confirmed
- hold
- intake_sent
- intake_received
- pricing_review
- quote_sent
- quote_accepted
- awaiting_confirmation
- confirmed
- upcoming
- delivered
- picked_up
- completed
- cancelled
- lost

### `source` Options:

- facebook_marketplace
- facebook_referral
- word_of_mouth
- repeat_customer
- other

### `delivery_method` Options:

- normal_delivery
- customer_pickup
- other

### Constraints:

- `requested_bench_count > 0`
- `confirmed_bench_count > 0`
- Monetary values cannot be negative
- `inventory_return_at > inventory_out_at`
- `pickup_at >= delivery_at`

### Recommended Booking Number Format:

- BR-2027-001
- BR-2027-002
etc.

## `booking_contacts` Table

### `contact_role` Options:

- contract_signer
- primary_customer
- secondary_customer
- venue_contact
- delivery_contact
- venmo_payer
- other

### Unique Constraint

booking_id + customer_id + contact_role

## `inventory_blocks` Table

### Constraints

- `quantity > 0`
- `end_at > start_at` when `end_at` exists

## `holds` Table

### `status` Options:

- active
- expired
- released
- converted

### Constraints

- `quantity > 0`
- `inventory_end_at > inventory_start_at`
- `expires_at > created_at`

## `intake_submissions` Table

### `review_status` Table

- pending
- accepted
- needs_clarification
- superseded

### Unique Constraint

booking_id + submission_number

## `pricing_rules` Table

### `rule_type` Options:

- bench_rate
- minimum_rental
- delivery_base
- delivery_mileage
- small_order_fee
- rehearsal_fee
- overnight_fee
- additional_day
- setup_fee
- deposit
- discount
- custom

### `calculation_method` Options:

- flat
- per_bench
- per_mile
- percentage
- tiered
- minimum
- manual

### Unique Constraint:

rule_code + effective_from

## `quotes` Table

### `status` Options:

- draft
- sent
- viewed
- accepted
- declined
- expired
- superseded

### Constraints

- All money fields >= 0
- `deposit_required <= total`
- `balance_after_deposit = total - deposit_required`
- Unique: `booking_id` + `version_number`

## `quote_items` Table

### `item_type` Options:

- bench_rental
- delivery
- mileage
- duration
- rehearsal
- overnight
- setup
- discount
- surcharge
- custom

## `contract_templates` Table

### Unique Constraint

name + version_number

## `contracts` Table

### `status` Options:

- draft
- generated
- sent
- viewed
- signed
- declined
- voided
- superseded

### Unique Constraint

booking_id + version_number

## `expected_payments` Table

### `payment_type` Options:

- deposit
- final_balance
- additional_charge
- damage_charge
- refund
- other

### `status` Options:

- expected
- verification_needed
- partially_received
- received
- waived
- cancelled
- overdue
- refunded

### `expected_method` Options:

- venmo
- cash
- check
- other

### Constraint

- `expected_amount > 0`

## `payments` Table

### `transaction_direction` Options:

- received
- refunded

### `verification_status` Options:

- pending
- verified
- rejected

### Constraint

- `amount > 0`

## `booking_changes` Table

### `change_category` Options:

- contact
- venue
- inventory
- timing
- pricing
- payment
- contract
- status
- other

### `source` Options:

- facebook
- text
- phone
- email
- in_person
- customer_form
- internal
- other

## `communications` Table

### `direction` Options:

- incoming
- outgoing
- internal

### `channel` Options:

- facebook
- text
- phone
- email
- in_person
- system
- other

### `communication_type` Options:

- availability_response
- intake_sent
- quote_sent
- quote_reminder
- contract_sent
- contract_reminder
- deposit_reminder
- confirmation
- delivery_reminder
- change_confirmation
- pickup_message
- general

## `tasks` Table

### `task_type` Options:

- follow_up
- review_intake
- prepare_quote
- verify_payment
- contract_follow_up
- delivery
- pickup
- customer_change
- other

### `priority` Options:

- low
- normal
- high
- urgent

### `status` Options:

- open
- in_progress
- completed
- cancelled

## `documents` Table

### `document_type` Options:

- venue_map
- payment_screenshot
- damage_photo
- customer_attachment
- contract_attachment
- delivery_photo
- other

### Unique Constraint

storage_bucket + storage_path

## `calendar_events` Table

### `event_type` Options:

- delivery
- event
- pickup
- hold_expiration
- payment_due
- other

### `sync_status` Options:

- pending
- synced
- failed
- deleted

### Unique Constraint (where available)

provider + external_event_id

## `business_settings` Table

### Example `setting_key` Values:

- business_name
- total_bench_count
- default_hold_hours
- default_quote_valid_hours
- default_state
- home_base_address
- service_radius_miles
- business_email
- mom_phone
- venmo_username
- venmo_phone_last_four
- deposit_policy
- booking_number_next_sequence

## All Needed Indices

- bookings(event_date)
- bookings(stage)
- bookings(inventory_out_at, inventory_return_at)
- bookings(primary_customer_id)
- bookings(venue_id)

- holds(status, expires_at)
- holds(inventory_start_at, inventory_end_at)

- customers(email)
- customers(phone)

- customer_identities(identity_type, display_value)

- quotes(booking_id, status)
- contracts(booking_id, status)

- expected_payments(booking_id, status)
- expected_payments(due_at)

- payments(booking_id)
- payments(actual_payer_name)

- tasks(status, due_at)
- tasks(assigned_to, status)

- calendar_events(booking_id)
- communications(booking_id, occurred_at)
- booking_changes(booking_id, changed_at)