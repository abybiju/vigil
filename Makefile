.PHONY: setup seed eval eval-fresh run test clean

# Provision a Python 3.13 venv and install everything (incl. dev group for tests).
# 3.13 matches the hosted (Streamlit Cloud) runtime; the code runs on any 3.11+.
setup:
	uv venv --python 3.13
	uv sync

# Initialise the SQLite DB, embed the FAQ corpus, load the labelled dataset.
seed:
	uv run python -m vigil.seed

# Run the eval harness (uses cached model outputs — re-runs are free).
eval:
	uv run python -m eval.run_eval

# Force fresh model calls (spends API tokens), overwriting the cache.
eval-fresh:
	uv run python -m eval.run_eval --no-cache

# Launch the Streamlit demo.
run:
	uv run streamlit run app.py

# Launch the webhook ingestion service (real-time intake; needs ANTHROPIC_API_KEY).
webhook:
	uv run uvicorn vigil.webhook:app --reload --port 8000

# Unit tests (pure functions; no API calls).
test:
	uv run pytest

clean:
	rm -f vigil.db vigil.db-wal vigil.db-shm
