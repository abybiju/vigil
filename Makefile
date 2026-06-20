.PHONY: setup seed eval eval-fresh run test clean

# Provision a Python 3.11 venv and install everything (incl. dev group for tests).
setup:
	uv venv --python 3.11
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

# Unit tests (pure functions; no API calls).
test:
	uv run pytest

clean:
	rm -f vigil.db vigil.db-wal vigil.db-shm
