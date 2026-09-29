# bench-rentals

## Local development

Install dependencies with `uv sync`. Start the app from the repository root
on local port 8502:

```powershell
uv run streamlit run app.py --server.port=8502
```

The app will be available at http://localhost:8502. The command-line port
override applies only to this local launch.
Keep credentials in the ignored `.streamlit/secrets.toml` file.

## Deployment

Streamlit Community Cloud runs `app.py` from the `main` branch. With no
repository port override, it uses the default port 8501 expected by its health
check. The tracked `.streamlit/config.toml` contains the shared warm green
theme and no server port override, so local and deployed apps share the same
appearance. Keep local-only server options in launch commands and credentials
in the ignored secrets file.

## Inquiry link sharing (Phase 5.2)

Home and the Bookings list have a **Copy inquiry link** control. Once enabled,
it opens a panel with the complete URL. Use the copy icon, or select and copy the
URL manually, then paste it into the customer's existing conversation. Copying
does not create a booking, send a message, or reserve benches.

**Leave `PUBLIC_INQUIRY_URL` unset until Phase 5.4 delivers the public form.**
The control stays disabled and displays “Inquiry form sharing isn’t available
yet.” No Supabase SQL or database setup is needed for Phase 5.2.

When the customer form is ready:

1. Open its complete HTTPS URL while signed out (for example, in a private
   browser window). Verify that it shows the customer inquiry form without
   requiring internal sign-in. Verify the form's submission workflow as part of
   Phase 5.4 before enabling sharing.
2. Set `PUBLIC_INQUIRY_URL` as a top-level string in Streamlit Community Cloud's
   deployment secrets. For local development use the ignored
   `.streamlit/secrets.toml`; do not add it to the shared theme configuration.
   The example below is deliberately commented out:

   ```toml
   # Enable only after verifying the real public form URL in Phase 5.4:
   # PUBLIC_INQUIRY_URL = "https://your-public-host.example/inquiry"
   ```

3. Refresh the workspace, open **Copy inquiry link**, and verify that pasting
   copies exactly the configured URL on both Home and Bookings. Check on desktop
   and phone. Opening the panel alone does not copy or send anything.

The setting must be a complete HTTPS URL with a valid hostname. It must not
contain credentials, query strings, fragments, or internal whitespace. Leading
and trailing whitespace is trimmed. Use the reusable initial inquiry URL,
not an internal booking route, a customer-specific private link, or localhost.
The app neither derives this URL from the current page nor checks its availability
over the network; setting it explicitly enables sharing.

If **The inquiry link is unavailable.** appears, check the setting's spelling,
string type, URL format, and secrets-file syntax. Invalid configuration disables
sharing without displaying the raw value. A missing or blank setting leaves the
feature unconfigured. If the browser refuses clipboard access, select the URL
in the panel and copy it manually. Remove or blank the setting to disable sharing.
