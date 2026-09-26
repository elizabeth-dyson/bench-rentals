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
