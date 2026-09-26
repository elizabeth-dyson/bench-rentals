# 1. Foundation ✅

GitHub repo, Streamlit app, deployment, Supabase project, database schema, basic RLS.

# 2. Authentication

Add login, create you/Mom/Dad as users.

# 3. App Navigation + Home Screens

Build the overall Streamlit structure: navigation, dashboard, admin/settings area, mobile-friendly layout.

# 4. Bookings / Leads

Build the first complete internal lead-management loop in small increments. By the end, Mom can record a serious inquiry, find it later, review and update its information, and mark it lost or cancelled. Availability, holds, intake, pricing, quotes, payments, and confirmation remain later phases.

## 4.1 Bookings Foundation

- Activate Bookings in the sidebar.
- Add the Bookings page and booking-service layer.
- Handle loading, empty, and database-error states cleanly.
- Establish reusable formatting for booking stages, dates, and customer names.

## 4.2 Active Leads List

- Make active leads the default Bookings view.
- Show the customer, event date, requested bench count, and current stage.
- Order leads so the most relevant upcoming inquiries are easiest to find.
- Keep the layout usable as both a desktop table/list and mobile cards.

## 4.3 Create a Lead

- Add a mobile-friendly lead form.
- Require customer name, event date, requested bench count, and at least one contact method.
- Support email, phone/text, or Facebook contact information.
- Save the customer, contact identity, booking relationship, and booking record using the existing schema.
- Detect likely existing customers and reuse them instead of silently creating duplicates.

## 4.4 Booking Detail

- Open a booking from the list into a clear detail view.
- Display its booking number, stage, customer/contact information, event details, requested benches, source, and notes.
- Provide clear actions for editing or returning to the list.
- Leave future workflow sections such as pricing, contracts, and payments out for now.

## 4.5 Edit Lead Information

- Allow updates to the core customer, contact, event, bench-count, source, and notes fields.
- Apply the same validation rules used during creation.
- Warn before abandoning unsaved changes.
- Do not implement formal booking-change history yet; that remains Phase 12.

## 4.6 Search and Filters

- Search across recognizable booking information such as customer name, contact details, and booking number.
- Filter by stage and event-date range.
- Provide access to all records while continuing to emphasize active leads by default.
- Include a simple way to clear filters and return to the active-leads view.

## 4.7 Lead Disposition

- Allow a lead to be marked lost or cancelled.
- Confirm the action before changing the stage.
- Keep closed records searchable rather than deleting them.
- Allow an incorrectly closed record to be restored to lead.
- Do not permit manual jumps into later workflow-owned stages.

## 4.8 Phase Verification and Polish

- Test the complete create → find → view → edit → close → restore flow.
- Test customer matching and contact-method validation.
- Verify empty, invalid, duplicate, and database-failure states.
- Run the workflow on desktop and phone layouts.
- Confirm authenticated RLS access remains enforced.

## Interfaces and Boundaries

- Add focused booking/customer service functions rather than querying Supabase directly from page code.
- Reuse the existing bookings, customers, customer_identities, and booking_contacts tables without schema or RLS changes.
- The Phase 4 UI may set only lead, lost, and cancelled; later phases own all other stage transitions.
- A valid contact means email, phone for text/call, or a Facebook identity consistent with the selected preferred contact method.

## Assumptions

- Booking-number generation will use the existing database design and be finalized during the detailed plan for lead creation.
- Active leads initially means records in the lead stage; the active view can expand as later workflows are implemented.
- Each numbered piece receives its own detailed implementation plan before coding.
- No customer-facing forms, inventory decisions, pricing, communication automation, or database redesign are part of Phase 4.

# 5. Availability + Holds

Build the next complete internal workflow in small increments. By the end, Mom can check whether enough benches are available for the full rental window, place a temporary hold, and manage its expiration or release without overbooking inventory. A successful availability check does not reserve benches; an active hold does. Customer intake and permanent booking confirmation remain later phases.

## 5.1 Availability Rules and Foundation

- Establish focused availability, inventory, and hold service functions using the existing database design.
- Verify the deployed schema against `docs/DATABASE.md` before implementing database changes.
- Read and validate `total_bench_count` and `default_hold_hours` from `business_settings`; document how to initialize them without building the full Settings area.
- Define which booking stages consume inventory, which quantity to use for confirmed rentals, and how holds remain effective as bookings move through later pre-confirmation stages.
- Agree on the inventory-window boundary and turnaround rules, using the app's existing America/Chicago business timezone.
- Show an actionable setup or data error when required settings or inventory records are incomplete rather than reporting misleading availability.

## 5.2 Rental Inventory Window

- Add inventory-out and inventory-return date/time fields to the booking workflow.
- Keep the inventory window separate from the event date and eventual delivery/pickup appointment details.
- Cover early delivery, overnight rentals, rehearsal use, and return/turnaround time within the period that benches are unavailable.
- Require a positive bench count and a complete, correctly ordered inventory window before checking availability or placing a hold.
- Let existing Phase 4 leads supply these details when needed without making them required during initial lead creation.
- Display local times clearly and store timezone-aware timestamps consistently.

## 5.3 Availability Calculation

- Calculate available benches throughout the requested window using total inventory, inventory-consuming bookings, unexpired active holds, and active inventory blocks.
- Use the lowest available quantity during the window; do not simply add every record that overlaps some part of it when those records do not overlap each other.
- Handle partial overlaps, rentals spanning several days, adjacent windows, and inventory blocks with no end date.
- Exclude expired, released, and converted holds from temporary demand, and avoid counting a confirmed booking and its former hold twice.
- When rechecking an existing hold, replace its current demand with the proposed demand rather than counting it against itself.
- Return enough information to explain available quantity, shortages, and the bookings or blocks causing a conflict.

## 5.4 Availability Check Workflow

- Activate Availability in the sidebar with a mobile-friendly bench-count and date/time check.
- Offer the same check from booking detail, prefilled from the booking's requested count and inventory window.
- Show a clear available/unavailable result, remaining capacity, and overlapping commitments with links to their booking details.
- Allow a successful booking-specific check to move a lead to `availability_confirmed`; explain that this records a check, not a reservation or guarantee of future availability.
- Invalidate displayed results when inputs change and provide a fresh check before proceeding.
- Handle empty schedules, invalid input, missing setup, and database failures cleanly.

## 5.5 Place a Temporary Hold

- Let Mom review the booking, quantity, inventory window, and expiration before placing a hold.
- Use the configured default hold duration and clearly display the expiration in local time.
- Recheck capacity and create the hold in one database transaction so two users cannot reserve the same remaining benches.
- Prevent duplicate effective holds for one booking, including repeated submissions and retries after an uncertain save result.
- Update the hold, booking inventory fields, `hold_expires_at`, and the early booking stage together.
- Preserve the submitted details and explain conflicts if another action consumes capacity before the hold is saved.

## 5.6 Hold Expiration, Extension, and Release

- Show the current hold quantity, inventory window, expiration, and effective status on booking detail.
- Stop counting a hold as soon as its expiration is reached, using database time even when nobody has the app open.
- Reconcile stored expired statuses and booking summary fields through a repeatable process; availability must not depend on a cleanup job running on time.
- Allow deliberate extension or release of an active hold, with confirmation and a recorded reason for release.
- Require a fresh capacity check to reacquire an expired or released hold; never silently revive it.
- Keep prior hold records and distinguish expired, released, and eventually converted holds.

## 5.7 Inventory Blocks and Conflicts

- Add a small internal workflow for taking benches out of availability for maintenance, damage, or personal use.
- Record quantity, start, optional end, reason, and notes using `inventory_blocks`.
- Allow blocks to be edited or ended without deleting their records.
- Show affected bookings and holds before saving a block that reduces capacity below existing commitments; require explicit acknowledgment and keep the resulting conflict visible.
- Do not automatically release customer holds or cancel bookings to resolve an inventory shortage.
- Keep full inventory/settings administration in Phase 18.

## 5.8 Booking Workflow Integration

- Expand the default active view to include `lead`, `availability_confirmed`, and `hold` so progressing a lead does not make it disappear from Mom's workspace.
- Update the existing lead-only edit and disposition controls and RPC guards deliberately for these early workflow stages.
- Recheck availability and update booking/hold quantities and windows atomically when inventory-affecting details change; preserve the original hold if a proposed change fails.
- Require another availability check when changes invalidate a prior `availability_confirmed` result.
- Release any active hold atomically when an early-stage booking is marked lost or cancelled; restoring it returns to lead without restoring inventory rights.
- Return an early `hold` booking to lead when its hold expires or is released, while preserving later intake/quote stages and showing their missing-hold status separately.
- Define the handoff for Phase 6 intake changes and Phase 11 hold-to-reservation conversion without implementing those workflows yet.

## 5.9 Phase Verification and Polish

- Test the complete lead → inventory window → availability check → hold → extend/release/expire → recheck flow.
- Verify exact-capacity requests, shortages, partial and nested overlaps, non-simultaneous overlaps, adjacent windows, multi-day rentals, and open-ended blocks.
- Test expiration boundaries, timezone/daylight-saving transitions, and availability after expiration while the app was closed.
- Verify simultaneous hold attempts, duplicate submissions, failed changes, stale screens, and recovery after database errors against the database behavior as well as service/UI tests.
- Test inventory-affecting edits, closure and restoration, conflicting blocks, and confirmed-booking fixtures without double-counting inventory.
- Run the workflow on desktop and phone layouts, confirm authenticated RLS access remains enforced, and rerun the Phase 4 lead workflow checks.

## Interfaces and Boundaries

- Reuse `bookings`, `holds`, `inventory_blocks`, and `business_settings`; add only focused RPCs, constraints, or indexes needed for correctness, with deployment SQL and database documentation kept together.
- Keep Supabase access in services and enforce capacity checks and related writes in the database. Inventory-changing operations must share a concurrency strategy, including future confirmation and total-inventory changes.
- Treat `holds` as the source of truth for temporary reservations; keep `bookings.hold_expires_at` as a synchronized summary rather than a second independent reservation.
- Keep hold status separate from booking stage so an active hold can continue through intake, pricing, and quotes. Phase 5 owns the early `availability_confirmed` and `hold` transitions; later phases own their own transitions.
- Include existing confirmed rentals in availability calculations, but leave permanent reservation creation/conversion and confirmation requirements to Phase 11.
- Full booking-change history remains Phase 12; customer messages, calendar sync, pricing, payments, contracts, and general admin tools remain outside Phase 5.

## Assumptions

- Benches are interchangeable and managed by quantity, not by individual bench identifiers.
- The approximate inventory count in the database documentation is context, not a hardcoded capacity; confirm the real count and hold duration during 5.1.
- Proposed interval rule: inventory is unavailable from the start up to, but not including, the return time; any required turnaround buffer is included before that return time. Finalize this in 5.1 before implementing overlap checks.
- Event date alone is insufficient to promise inventory; a provisional inventory window is needed before customer intake and can be revised through the guarded workflow.
- Each numbered piece receives its own detailed implementation plan before coding, including any business-rule decisions left open above.
- This breakdown does not mark Phase 4.8 validation complete; finish that validation before implementing Phase 5.

# 6. Customer Intake Form

Once Mom confirms availability and the customer says yes, generate a private form link so the customer can provide all the official contact, venue, delivery, pickup, and rental details.

# 7. Pricing System

Formalize Mom’s pricing rules, calculate a suggested price, flag unprofitable/small deliveries, and let Mom override the recommendation.

# 8. Quotes

Turn pricing into a clean customer quote, allow revisions, send it, track acceptance/expiration, and preserve old quote versions.

# 9. Payments / Dad Workflow

Create expected deposits and balances, let Dad see who is supposed to Venmo him, record the actual Venmo payer, and verify payments himself.

# 10. Contracts + E-Signatures

Generate contracts from booking data, send them electronically for signature, store signed copies, and track contract status.

# 11. Automatic Confirmation Logic

When the signed contract and deposit are received, automatically mark the rental confirmed and convert the temporary hold into a real reservation.

# 12. Booking Changes + History

Let Mom update delivery times, pickup times, bench counts, venue details, etc., while preserving what changed, when, why, and whether the customer was notified.

# 13. Day-of Operations

Build the glorious “Today” screen: address, directions, customer phone, bench count, current delivery/pickup time, notes, balance owed, and payment status all in one place.

# 14. Completion / Cancellation Workflow

Mark benches delivered, picked up, rental complete, lost lead, cancelled booking, refunded deposit, etc.

# 15. Customer Communication

Build reusable emails/messages for forms, quotes, contract reminders, confirmations, payment reminders, delivery reminders, and changes.

# 16. Calendar Integration

Sync confirmed deliveries and pickups with Google Calendar and keep them updated if logistics change.

# 17. Documents + Storage

Set up Supabase Storage for contracts, payment screenshots, venue maps, delivery photos, damage photos, and other files.

# 18. Settings / Admin Tools

Manage bench inventory count, hold durations, pricing rules, deposit rules, contract templates, business info, Venmo instructions, service area, and users.

# 19. Reports

Revenue, number of rentals, outstanding balances, average booking size, busiest months, common venues, booking lead time, lost inquiries, and eventually other useful little business nerd stats.

# 20. Testing + Hardening

Run fake bookings through every weird scenario, tighten RLS, test permissions, test mobile, handle failures, backups, error states, and security.

# 21. Historical Data + Real Future Bookings

Enter a handful of old rentals for testing/context and then enter any actual spring/summer bookings Mom receives over the winter.

# 22. Mom + Dad Usability Testing

Make them actually use it. Watch where they get confused. Simplify ruthlessly. This will absolutely reveal things neither of us thought of.

# 23. Preseason Launch

Clean up the UI, finalize pricing/contracts, make sure phone shortcuts are set up, and officially switch Mom away from her current scattered system.

# 24. Later / Optional Fancy Stuff

SMS automation, mileage APIs, customer portal, automatic payment integrations if feasible, better analytics, more polished frontend, or eventually replacing Streamlit with something like Next.js if Streamlit becomes limiting.
