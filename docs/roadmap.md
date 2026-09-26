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

Build the “Are 14 benches available this weekend?” logic, temporary holds, expiration, overlapping rentals, and inventory conflicts.

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