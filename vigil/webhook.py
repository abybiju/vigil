"""FastAPI webhook ingestion service for Vigil.

A support platform POSTs a message to `/webhooks/{platform}`; the matching adapter
normalizes it, the live pipeline triages + routes it, and the case is written to the
same DB the Streamlit dashboard reads. Run with: `make webhook` (needs ANTHROPIC_API_KEY).

Endpoints:
  GET  /healthz                  -> liveness
  GET  /                         -> service info + supported platforms
  POST /webhooks/{platform}      -> ingest one message (platform: gorgias|zendesk|shopify|email|generic)
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException

from . import db
from .adapters import ADAPTERS
from .llm import get_client
from .realtime import ingest_and_process
from .retrieve import load_retriever

app = FastAPI(title="Vigil ingestion", version="0.1.0")

# Lazily-built singletons; tests override the dependency functions below.
_state: dict = {}


def get_client_dep():
    if "client" not in _state:
        _state["client"] = get_client()
    return _state["client"]


def get_retriever_dep():
    if "retriever" not in _state:
        conn = db.init_db()
        _state["retriever"] = load_retriever(conn)
        conn.close()
    return _state["retriever"]


def get_conn_dep():
    conn = db.get_conn()
    try:
        yield conn
    finally:
        conn.close()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/")
def info():
    return {
        "service": "vigil-ingestion",
        "platforms": sorted(ADAPTERS),
        "post_to": "/webhooks/{platform}",
        "note": "Detection & triage aid with a human gate. A clinical case is never auto-answered.",
    }


@app.post("/webhooks/{platform}")
def ingest_webhook(
    platform: str,
    payload: dict,
    conn=Depends(get_conn_dep),
    client=Depends(get_client_dep),
    retriever=Depends(get_retriever_dep),
):
    adapter = ADAPTERS.get(platform)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"unknown platform '{platform}'. Supported: {sorted(ADAPTERS)}")

    raw = adapter(payload)
    if not (raw.get("raw_text") or "").strip():
        raise HTTPException(status_code=422, detail="could not extract message text from payload")

    return ingest_and_process(conn, client, raw, retriever=retriever)
