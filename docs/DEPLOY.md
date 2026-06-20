# Deploying the Vigil demo

The Vigil UI is a **Streamlit** app. It reads from SQLite and makes **no API calls in the render
path**, so the hosted demo needs **no API key and incurs no runtime cost** — it ships with a bundled
read-only snapshot (`demo.db`, 97 pre-processed cases) that the app falls back to automatically.

## ⚠️ Vercel won't work for this app

Vercel hosts serverless functions and static/Next.js frontends. Streamlit needs a **long-running
server with WebSockets**, which Vercel's execution model does not support. Use one of the hosts below
instead. (If a Vercel-hosted *frontend* is a hard requirement, that would mean rebuilding the UI as a
Next.js app against a separate API — a much larger effort, deferred in the build plan in favor of
Streamlit.)

## Recommended: Streamlit Community Cloud (free, ~2 minutes)

The repo is already deploy-ready (`requirements.txt` + bundled `demo.db`).

1. Go to **https://share.streamlit.io** and sign in with GitHub.
2. **Create app** → **Deploy a public app from GitHub**.
3. Repository: `abybiju/vigil` · Branch: `main` · Main file path: `app.py`.
4. Click **Deploy**. No secrets needed — the app auto-loads `demo.db`.

You get a public URL like `https://abybiju-vigil.streamlit.app`.

> To run the live model pipeline on the host instead of the bundled snapshot (not recommended for a
> public URL — it would spend your API credits on every visitor), add `ANTHROPIC_API_KEY` under the
> app's **Settings → Secrets** and run `make seed && make eval` against the host's DB.

## Alternative: Hugging Face Spaces (free)

Create a **Streamlit** Space, push this repo to it. `requirements.txt` + `demo.db` are picked up
automatically; set the app file to `app.py`.

## Alternative: Render / Railway (free tier)

Web service, build `pip install -r requirements.txt`, start command:

```
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

## Run locally

```bash
make setup && make seed && make eval && make run   # needs ANTHROPIC_API_KEY in .env
```
