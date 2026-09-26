# bench-rentals

## Local development

Install dependencies with `uv sync`. To use port 8502 locally, create
`.streamlit/config.toml` with:

```toml
[server]
port = 8502
```

Start the app from the repository root:

```powershell
uv run streamlit run app.py
```

The app will be available at http://localhost:8502. The configuration file is
ignored by Git, so this local port setting is not included in deployments.
Keep credentials in the ignored `.streamlit/secrets.toml` file.

## Deployment

Streamlit Community Cloud runs `app.py` from the `main` branch. With no
repository port override, it uses the default port 8501 expected by its health
check. Keep `.streamlit/config.toml` untracked; future shared configuration or
theme settings will need a separate approach to preserve the local port choice.
