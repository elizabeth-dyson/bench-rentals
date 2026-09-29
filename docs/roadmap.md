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

# 5. Intake + Inquiry Creation

Build on the completed Phase 4 foundation. The normal business flow is: customer contacts Mom → Mom sends an inquiry-form link → customer submits it → the app creates the inquiry → Mom reviews → quote → acceptance, contract/deposit, and confirmation in later phases. Mom can alternatively enter the same inquiry information for a phone/offline customer through the same underlying creation pipeline.

Phases 1–4 are complete and retained as written. Extend their customer, booking, validation, matching, search, detail, edit, and disposition work. Existing leads and their identifiers remain usable without re-entry.

## 5.1 Shared Inquiry Model

- Keep `bookings` as the canonical record from inquiry through completed rental. New inquiries can use the existing `lead` stage; do not add a separate leads table or create another booking when an inquiry progresses.
- Verify the deployed schema against `docs/DATABASE.md` before implementing focused database changes.
- Define shared inquiry fields for name/contact details, event date/type, requested benches, venue/address, delivery or pickup preference, relevant timing, and customer instructions.
- Retain the minimum requirements of name, event date, positive bench count, and a usable contact method. Decide which additional fields are required at submission and which Mom can clarify before pricing.
- Keep current working values in booking/customer/venue records and original submitted answers in `intake_submissions`. Later edits must not rewrite the original answers.
- Separate customer-wide notes, rental-specific notes, and internal notes instead of copying one field into both customer and booking records.
- Record entry method (`public_form` or `staff_entered`) separately from referral source, such as Facebook or word of mouth.

### 5.1 Agreed Requirements and Implementation Boundary

- Only name, event date, positive bench count, and a usable contact method are
  required. Venue/address, event type, delivery preference, and timing may be
  clarified before pricing.
- Delivery preferences are family delivery, customer pickup, and unsure.
  Existing third-party/other values on older records remain usable.
- Capture optional structured delivery, setup, event-start, pickup, and rehearsal
  timestamps plus timing notes in America/Chicago. Do not infer an inventory
  window or confirmed appointment.
- Allow partial venues without inventing an address or default state.
- Implement the shared model and database foundation now, plus the existing
  lead workflow's note-separation fix. Current forms label rental-specific notes
  as “Rental notes”; customer-wide note editing remains deferred.
- Preserve historical notes and unknown origins. New staff-created leads record
  `staff_entered`, separately from referral source.
- Public forms, full inquiry persistence/snapshot creation, review, and expanded
  staff entry remain 5.2–5.5. Do not fabricate submissions for older leads.
- Local implementation is present. The user installed the SQL on 2026-09-28;
  the full post-installation report verifies the expected schema, triggers,
  function bodies, and unchanged access settings. Isolated database integration
  tests and desktop/phone workflow checks remain pending; see `docs/DATABASE.md`
  and `docs/INQUIRY_MODEL.md` for installation and verification instructions.

## 5.2 Send the Form Without Creating a Lead

- Give Mom a “Copy inquiry link” action to share through existing conversations without entering customer details first.
- Use a reusable public inquiry URL as the default initial-entry design. Retain booking-specific private links for later follow-up on an existing inquiry.
- If individual private invitations are chosen instead, allow them to exist without a booking and associate them upon submission. Do not create placeholder bookings just to issue a link.
- Do not require an availability check, hold, customer acceptance, or customer login before sending or submitting the initial form.
- Leave automated messaging and delivery tracking to Phase 15; copying and manually sending the link is enough here.

### 5.2 Implementation and Activation

- A shared **Copy inquiry link** popover is implemented on Home and the Bookings
  list, before database loading. It remains outside lead forms and booking detail.
- The panel uses Streamlit's built-in copy icon and selectable plain-text URL.
  It copies only the reusable URL; opening it does not imply copying or sending.
- Optional top-level `PUBLIC_INQUIRY_URL` in Streamlit secrets explicitly enables
  sharing. Missing/blank or invalid configuration disables the control. The URL
  must be absolute HTTPS without credentials, queries, fragments, or whitespace.
- Leave the setting unset until Phase 5.4. Verify the real public form while
  signed out before enabling it; see README for activation and troubleshooting.
- This phase creates no bookings, invitations, tokens, or submissions and makes
  no schema, RPC, RLS, authentication, or public-route changes. No SQL is needed.
- URL validation and rendering have automated coverage. Browser layout and actual
  clipboard/manual-copy checks remain pending when no browser is connected.

## 5.3 One Creation Pipeline

- Extend existing transactional creation so public submissions and staff entry share one underlying business operation and field validation.
- On successful submission, create the working booking in `lead`, customer/contact relationships, and original intake submission together. Reuse booking numbering and existing validation.
- `intake_submissions.booking_id` can remain required: create the booking before its submission within the same transaction, without prior manual entry.
- Record submission origin and staff attribution when applicable; public submissions must not require a staff user ID or accept staff-only fields.
- Prevent duplicate inquiries and submission versions from double clicks, retries after uncertain responses, and concurrent requests.
- Reuse customer matching where appropriate, but do not expose existing customers or let public callers select arbitrary customer IDs or overwrite shared customer information. Route uncertain matches to staff review.
- Attach follow-up information to existing Phase 4 bookings without changing their identifiers or creating another inquiry.

### 5.3 Agreed Behavior and Implementation Status

- The shared backend is implemented locally. The user's ending schema inspection
  verifies SQL installation in the inspected project. Isolated database integration
  and two-session concurrency verification remain pending user runs.
  See [Inquiry persistence](INQUIRY_PIPELINE.md) for contracts and installation order.
- Reuse an active customer automatically only when every supplied contact resolves
  uniquely to that same customer. No matches creates a customer; partial,
  conflicting, or ambiguous matches creates a separate customer needing review.
- Automatic and explicit staff reuse preserve the entire customer profile and
  identities. Store supplied answers and the original matching outcome for later
  review. Customer-wide note editing and match resolution remain deferred.
- Initial creation is atomic across customer/contact, optional partial venue,
  lead booking, and original submission. Original answers precede normalization;
  SQL derives and validates working values. No inventory/price/hold work is added.
- Follow-ups contain complete answers and append pending snapshots without
  replacing working records or prior review decisions. Accept new follow-ups only
  on open leads; restore lost/cancelled leads first. Keep legacy IDs and origins.
- Caller UUIDs, database fingerprints, unique constraints, and transaction locks
  protect retries and version allocation. A completed request remains replayable
  after closure. Different payload/context with the same key is a conflict.
- Authenticated staff wrappers use the private shared SQL operation. Public-origin
  behavior exists only privately for testing/future authorized wrappers; no anon
  grants, public route, private-link workflow, or service-role client is added.
- Current Add lead and other screens keep their existing behavior until 5.5.
  Inquiry sharing stays disabled until 5.4. Phase 5.3 is not database-verified
  complete until the isolated behavioral and concurrency scripts pass.

## 5.4 Customer Form and Access

- Build a mobile-friendly form accessible without signing in to the internal application.
- Show clear validation, preserve answers after recoverable failures, and confirm success only after the inquiry and submission are saved.
- Explain that submission requests a quote; it does not confirm a rental or reserve inventory.
- Provide narrowly scoped server-side submission access while preserving internal RLS. Do not expose internal tables, customer searches, credentials, or staff notes.
- Enforce token validation, expiration, revocation, and resubmission rules for private follow-up links.
- Include appropriate input limits and abuse protection.

## 5.5 Staff Entry and Review

- Adapt “Add a lead” into “Enter inquiry,” collecting the same core information as the public form through the shared operation.
- Preserve a submission snapshot with staff attribution, existing customer-match review/reuse, and optional staff-only context.
- Show new inquiries in the existing workspace with “New inquiry” or “Needs review” labeling.
- Use submission `review_status` and review metadata for pending, accepted, needs clarification, and superseded answers.
- Keep new bookings in `lead` initially to preserve existing list/edit behavior. Update queries and guarded actions deliberately as later phases add active stages.
- Let Mom inspect original answers alongside working values, resolve matches, and clarify venue/logistics details before pricing.
- Preserve earlier submissions when follow-up answers arrive; define which proposed changes require review before replacing working values.
- Accepting intake information means it is ready for the next business step, not that a quote or rental is confirmed.
- Keep search, detail, edit, close, and restore usable for older leads and new inquiries. Full booking-change history remains Phase 12.

## 5.6 Phase Verification and Polish

- Test send link → submission → one saved inquiry → dashboard visibility → review → clarification, plus staff entry through the same pipeline.
- Verify consistent working records, retry/concurrency protection, ambiguous customer matches, invalid input, failed saves, and recovery without partial records.
- Verify public access restrictions and private-link expiration/revocation/resubmission where applicable.
- Confirm follow-up submissions preserve existing Phase 4 records and identifiers.
- Confirm working-record edits do not rewrite original submitted answers.
- Test desktop and phone layouts and retain regression coverage for the completed Phase 4 workflow.

## Interfaces and Boundaries

- Reuse existing booking, customer, identity, contact, venue, intake-link, and submission tables where they fit. Keep focused database changes and documentation together.
- Keep page rendering separate from business services and enforce multi-record writes transactionally.
- Public submission and staff entry share business rules while retaining distinct access permissions.
- Availability and holds remain separate in Phase 6; their unresolved business rules must not become prerequisites for inquiry creation.
- Pricing, quotes, payments, contracts, and confirmation remain Phases 7–11.
- Each numbered piece receives its own detailed implementation plan before coding.

# 6. Availability + Holds

Build availability checking around Phase 5 inquiries and existing Phase 4 records. A check does not reserve inventory. The hold work below preserves planned technical requirements, but whether/when holds are offered, their duration, and what blocks inventory remain business decisions to settle in 6.1 before implementing that behavior. Holds are not prerequisites for sending or submitting an inquiry. Permanent confirmation remains Phase 11.

## 6.1 Availability Rules and Foundation

- Settle when inventory becomes unavailable and whether/when Mom offers temporary holds; confirm the proposed behavior below before implementation rather than inferring it from the old phase order.
- Establish focused availability, inventory, and hold services using the existing database design.
- Verify the deployed schema against `docs/DATABASE.md` before implementing database changes.
- Read and validate `total_bench_count` and `default_hold_hours` from `business_settings`; document how to initialize them without building the full Settings area.
- Define which booking stages consume inventory, which quantity to use for confirmed rentals, and how holds remain effective as bookings move through later pre-confirmation stages.
- Agree on the inventory-window boundary and turnaround rules, using the app's existing America/Chicago business timezone.
- Show an actionable setup or data error when required settings or inventory records are incomplete rather than reporting misleading availability.

## 6.2 Rental Inventory Window

- Add inventory-out and inventory-return date/time fields to the booking workflow.
- Keep the inventory window separate from the event date and eventual delivery/pickup appointment details.
- Cover early delivery, overnight rentals, rehearsal use, and return/turnaround time within the period that benches are unavailable.
- Require a positive bench count and a complete, correctly ordered inventory window before checking availability or placing a hold.
- Use submitted timing as input for Mom to establish the inventory window. Let existing leads and new inquiries supply missing details when needed without requiring a complete inventory window just to submit an inquiry.
- Display local times clearly and store timezone-aware timestamps consistently.

## 6.3 Availability Calculation

- Calculate available benches throughout the requested window using total inventory, inventory-consuming bookings, unexpired active holds, and active inventory blocks.
- Use the lowest available quantity during the window; do not simply add every record that overlaps some part of it when those records do not overlap each other.
- Handle partial overlaps, rentals spanning several days, adjacent windows, and inventory blocks with no end date.
- Exclude expired, released, and converted holds from temporary demand, and avoid counting a confirmed booking and its former hold twice.
- When rechecking an existing hold, replace its current demand with the proposed demand rather than counting it against itself.
- Return enough information to explain available quantity, shortages, and the bookings or blocks causing a conflict.

## 6.4 Availability Check Workflow

- Activate Availability in the sidebar with a mobile-friendly bench-count and date/time check.
- Offer the same check from booking detail, prefilled from the booking's requested count and inventory window.
- Show a clear available/unavailable result, remaining capacity, and overlapping commitments with links to their booking details.
- Record successful checks without losing inquiry review or quote progress. Decide in 6.1 whether `availability_confirmed` remains useful as an early stage; explain that a check is not a reservation or guarantee.
- Invalidate displayed results when inputs change and provide a fresh check before proceeding.
- Handle empty schedules, invalid input, missing setup, and database failures cleanly.

## 6.5 Place a Temporary Hold

- Let Mom review the booking, quantity, inventory window, and expiration before placing a hold.
- Use the configured default hold duration and clearly display the expiration in local time.
- Recheck capacity and create the hold in one database transaction so two users cannot reserve the same remaining benches.
- Prevent duplicate effective holds for one booking, including repeated submissions and retries after an uncertain save result.
- Update the hold, booking inventory fields, `hold_expires_at`, and any agreed stage transition together without overwriting inquiry review or quote progress.
- Preserve the submitted details and explain conflicts if another action consumes capacity before the hold is saved.

## 6.6 Hold Expiration, Extension, and Release

- Show the current hold quantity, inventory window, expiration, and effective status on booking detail.
- Stop counting a hold as soon as its expiration is reached, using database time even when nobody has the app open.
- Reconcile stored expired statuses and booking summary fields through a repeatable process; availability must not depend on a cleanup job running on time.
- Allow deliberate extension or release of an active hold, with confirmation and a recorded reason for release.
- Require a fresh capacity check to reacquire an expired or released hold; never silently revive it.
- Keep prior hold records and distinguish expired, released, and eventually converted holds.

## 6.7 Inventory Blocks and Conflicts

- Add a small internal workflow for taking benches out of availability for maintenance, damage, or personal use.
- Record quantity, start, optional end, reason, and notes using `inventory_blocks`.
- Allow blocks to be edited or ended without deleting their records.
- Show affected bookings and holds before saving a block that reduces capacity below existing commitments; require explicit acknowledgment and keep the resulting conflict visible.
- Do not automatically release customer holds or cancel bookings to resolve an inventory shortage.
- Keep full inventory/settings administration in Phase 18.

## 6.8 Booking Workflow Integration

- Keep inquiries visible in the active workspace through review and agreed availability/hold stages; include quote stages when implemented.
- Extend Phase 5 review/edit and disposition controls and RPC guards deliberately for additional active stages.
- Recheck availability and update booking/hold quantities and windows atomically when inventory-affecting details change; preserve the original hold if a proposed change fails.
- Require another availability check when reviewed intake updates or staff edits invalidate a previous result.
- Release any active hold atomically when an early-stage booking is marked lost or cancelled; restoring it returns to lead without restoring inventory rights.
- If the agreed design uses an early `hold` stage, define expiration/release transitions without erasing inquiry review or quote progress; show missing-hold status separately.
- Integrate Phase 5 intake review so proposed quantity/timing changes are validated before altering inventory commitments. Define the Phase 11 confirmation handoff without implementing confirmation yet.

## 6.9 Phase Verification and Polish

- Test inquiry → reviewed inventory window → availability check, plus hold → extend/release/expire → recheck when the agreed business rules call for a hold.
- Verify exact-capacity requests, shortages, partial and nested overlaps, non-simultaneous overlaps, adjacent windows, multi-day rentals, and open-ended blocks.
- Test expiration boundaries, timezone/daylight-saving transitions, and availability after expiration while the app was closed.
- Verify simultaneous hold attempts, duplicate submissions, failed changes, stale screens, and recovery after database errors against the database behavior as well as service/UI tests.
- Test inventory-affecting edits, closure and restoration, conflicting blocks, and confirmed-booking fixtures without double-counting inventory.
- Test desktop and phone layouts, authenticated RLS, and regression coverage for Phase 4 leads and Phase 5 inquiries.

## Interfaces and Boundaries

- Reuse `bookings`, `holds`, `inventory_blocks`, and `business_settings`; add only focused RPCs, constraints, or indexes needed for correctness, with deployment SQL and database documentation kept together.
- Keep Supabase access in services and enforce capacity checks and related writes in the database. Inventory-changing operations must share a concurrency strategy, including future confirmation and total-inventory changes.
- Treat `holds` as the source of truth for temporary reservations; keep `bookings.hold_expires_at` as a synchronized summary rather than a second independent reservation.
- Keep hold status separate from inquiry review and quote progress. Phase 6 owns any agreed availability/hold transitions; later phases own their transitions. Sending an initial inquiry link never requires a hold.
- Include existing confirmed rentals in availability calculations, but leave permanent reservation creation/conversion and confirmation requirements to Phase 11.
- Full booking-change history remains Phase 12; customer messages, calendar sync, pricing, payments, contracts, and general admin tools remain outside Phase 6.

## Assumptions

- Benches are interchangeable and managed by quantity, not by individual bench identifiers.
- The approximate inventory count in the database documentation is context, not a hardcoded capacity; confirm the real count and hold duration during 6.1.
- Proposed interval rule: inventory is unavailable from the start up to, but not including, the return time; any required turnaround buffer is included before that return time. Finalize this in 6.1 before implementing overlap checks.
- Event date alone is insufficient to promise inventory. Establish a complete inventory window before checking or reserving capacity, not before accepting an inquiry; revise it through the guarded workflow.
- Each numbered piece receives its own detailed implementation plan before coding, including any business-rule decisions left open above.
- Build on the completed Phase 4 foundation and Phase 5 inquiry workflow; retain their regression coverage as inventory behavior is added.

# 7. Pricing System

Use Mom-reviewed inquiry details to formalize pricing rules, calculate a suggested price, flag unprofitable/small deliveries, and let Mom override the recommendation. Read current working booking/customer/venue values; original intake answers remain a historical snapshot.

# 8. Quotes

Turn pricing into a clean customer quote attached to the existing inquiry/booking, allow revisions, send it, track acceptance/expiration, and preserve old quote versions. Keep the same booking identity through quote acceptance and confirmation, and keep active quote work visible in the workspace.

# 9. Payments / Dad Workflow

Create expected deposits and balances, let Dad see who is supposed to Venmo him, record the actual Venmo payer, and verify payments himself.

# 10. Contracts + E-Signatures

Generate contracts from booking data, send them electronically for signature, store signed copies, and track contract status.

# 11. Automatic Confirmation Logic

When the signed contract and required deposit are received/verified, automatically mark the existing inquiry/booking confirmed. Enforce inventory commitment rules agreed in Phase 6, including a fresh transactional capacity check and conversion of an active hold when applicable. Do not require every inquiry to pass through a hold or create another booking at confirmation.

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

Run public and staff-entered inquiries through review → quote → acceptance → contract/deposit → confirmation, including existing Phase 4 records. Test clarification, retries, failures, permissions, mobile behavior, backups, error states, and security throughout.

# 21. Historical Data + Real Future Bookings

Enter a handful of old rentals for testing/context and then enter any actual spring/summer bookings Mom receives over the winter.

# 22. Mom + Dad Usability Testing

Make them actually use it. Watch where they get confused. Simplify ruthlessly. This will absolutely reveal things neither of us thought of.

# 23. Preseason Launch

Clean up the UI, finalize pricing/contracts, make sure phone shortcuts are set up, and officially switch Mom away from her current scattered system.

# 24. Later / Optional Fancy Stuff

SMS automation, mileage APIs, customer portal, automatic payment integrations if feasible, better analytics, more polished frontend, or eventually replacing Streamlit with something like Next.js if Streamlit becomes limiting.
