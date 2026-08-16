# 1. Foundation ✅

GitHub repo, Streamlit app, deployment, Supabase project, database schema, basic RLS.

# 2. Authentication

Add login, create you/Mom/Dad as users.

# 3. App Navigation + Home Screens

Build the overall Streamlit structure: navigation, dashboard, admin/settings area, mobile-friendly layout.

# 4. Bookings / Leads

Build the core booking record flow: create a serious lead, see its status, edit it, search bookings, and move it through the booking lifecycle.

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