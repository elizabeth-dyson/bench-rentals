# Working on Bench Rentals

## Purpose and scope

This is currently a Streamlit application backed by Supabase/PostgreSQL. Keep
building the current product while preserving the option to replace the UI with
React/Next.js later. A future migration could retain Python behind an API or
port application logic to TypeScript while retaining Supabase and its SQL RPCs.
Do not assume either approach has been selected.

- Apply these boundaries to new code and code materially changed by the task.
  Existing exceptions are incremental cleanup opportunities, not a requirement
  to refactor unrelated code before completing a feature.
- Prefer small, explicit functions and models. Do not add a second frontend,
  HTTP API, generic repository framework, or new dependency solely for a
  hypothetical migration.
- Preserve unrelated working-tree changes. Do not reset, overwrite, or commit
  someone else's work as part of a task.

## Read before changing behavior

- Use `README.md` for setup and deployment, `docs/roadmap.md` for feature scope
  and unresolved business decisions, and `docs/DATABASE.md` for database design.
- Read the relevant roadmap section before implementing a workflow. Do not
  silently implement later phases or turn proposed rules into settled behavior.
- For roadmap features, outline the affected layers and verification before
  coding. Resolve missing business decisions with the user; make routine
  implementation choices within the authorized task without extra approval.
- The deployed database is authoritative when it disagrees with documentation.
  Inspect the live schema when a database change depends on its exact state. If
  that is unavailable, state the assumption and provide verification steps;
  never claim a local SQL file has been deployed or verified remotely.

## Keep the UI replaceable

- `app.py`, `views/`, and `components/` own rendering, widgets, navigation,
  query parameters, and transient UI state. Pages call focused services instead
  of issuing application-table queries or RPCs directly.
- Keep validation, normalization, customer matching, stage rules, availability,
  pricing, and other business calculations outside rendering functions.
  Extract reusable record-to-input transformations from pages as they grow.
- Core business functions accept explicit inputs and return values or raise
  meaningful exceptions. They must not read Streamlit session state, secrets,
  cookies, widgets, or routes, or call rendering/rerun functions.
- Business logic must not import UI modules. Keep pure models and calculations
  separate from modules that initialize clients or depend on Streamlit, so they
  can be imported and tested without starting the app.
- Pass the authenticated Supabase client or a narrowly scoped dependency into
  new service operations. Create/manage that client at the application boundary;
  do not add new hidden dependencies on `get_supabase_client()` in core logic.
  Avoid optional fallbacks that silently reintroduce Streamlit session access.
- Existing `services/supabase.py` and `services/auth_session.py` are Streamlit
  adapters despite their folder name. Keep session restoration, browser cookie
  handling, and configuration there or in another explicit adapter; do not copy
  those dependencies into business services.
- Session state may hold draft forms, selections, and pending UI actions. Saved
  bookings, workflow progress, reservations, and other durable business facts
  belong in the database.

## Make service contracts explicit

- Use typed inputs and results for new operations, following the existing lead
  dataclasses. Define focused summary/detail models for new read boundaries
  rather than spreading `dict[str, Any]` and nested Supabase joins through pages.
- Keep table names, relationship selectors, RPC parameters, and response parsing
  inside data-access/service code. Translate database responses at that boundary.
- Make public identifiers, optional fields, date/time meanings, and error outcomes
  explicit. If adding an HTTP boundary, define its serialization deliberately;
  do not expose Python objects or raw database errors as the API contract.
- Preserve useful error distinctions, such as validation, missing records,
  conflicts/stale state, and infrastructure failures. The UI owns user-facing
  feedback; logs must not expose credentials or unnecessary customer data.
- Pass the business date/time into calculations where practical. Use the existing
  `America/Chicago` business timezone; keep event dates distinct from timestamps.
  Use timezone-aware timestamps and decimal arithmetic for money.

## Preserve database correctness and access boundaries

- Reuse the documented schema. `bookings` is the canonical record across the
  rental lifecycle; preserve booking IDs/numbers as workflows advance. Do not
  introduce duplicate lead, user, or workflow tables without a concrete need.
- Keep multi-record writes and concurrency-sensitive invariants transactional in
  PostgreSQL. Extend the focused RPC pattern for operations that require atomic
  writes, guarded stage transitions, or inventory commitments.
- UI validation provides feedback; trusted server/database boundaries enforce
  authoritative rules. A second UI must not need to reproduce a hidden page
  check to perform a valid operation safely.
- Do not assume an RPC is the only possible write path. The current documented
  internal RLS policy allows authenticated CRUD. When adding an invariant, account
  for allowed write paths and use suitable constraints, triggers, or deliberately
  scoped access changes where enforcement requires them.
- Design retry protection for operations that create durable records or trigger
  external effects. Enforce concurrent capacity decisions transactionally rather
  than relying on an earlier UI availability check.
- Keep authenticated clients scoped to their user/session (or request in a future
  backend). Never cache them globally or use a service-role key to work around RLS.
  Keep credentials out of source control, browser output, logs, and test fixtures.
- Preserve the current equally trusted internal-user model. Public inquiry and
  private-link workflows need narrow access of their own; do not grant public
  callers internal table access or trust supplied customer IDs/staff-only fields.
- Preserve historical submissions and business records according to the roadmap;
  prefer explicit cancellation/archive workflows to destructive deletion.
- Put database changes in reviewable SQL under `supabase/`, with installation and
  verification instructions. Keep `docs/DATABASE.md` aligned with deployed changes
  and clearly label changes that remain pending installation. Do not recreate the
  database or introduce a migration framework just to complete an unrelated task.
- The user runs Supabase SQL manually. Prepare the SQL files and give the exact
  copy/paste execution order, distinguishing installation from inspection and
  test-only scripts. Do not execute SQL against Supabase unless the user explicitly
  requests it. Keep deployment status pending until the user confirms execution.

## Verify proportionately

- Use `uv` and the existing environment. Install/sync dependencies only as needed.
  Local launch: `uv run streamlit run app.py --server.port=8502`. Keep local port
  overrides out of the shared deployment configuration.
- Run focused existing tests for the changed behavior. The full unittest command
  is `uv run python -m unittest discover -s tests`. Report what actually ran and
  any environment limitations; do not imply unrun checks passed.
- Test business rules independently of Streamlit. Use UI/AppTest coverage for
  meaningful user flows, and database integration checks for changed SQL, RLS,
  transaction, or concurrency behavior. Mocked RPC responses do not verify SQL.
- Database integration checks must use an isolated test environment or safely
  scoped fixtures; do not create, alter, or delete real customer records to test.
- Exercise invalid input, failed writes, stale state, and retries when relevant.
  Check phone and desktop layouts for meaningful UI changes. Documentation-only
  edits do not require application tests.
- Summarize the resulting behavior, verification, and any remaining deployment
  work. Keep changes focused; add abstractions or tests when they protect a real
  boundary or behavior rather than mirroring implementation details.
