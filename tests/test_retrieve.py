"""TF-IDF retrieval: returns the relevant chunk with citation metadata, end-to-end via DB."""

import pytest

from vigil import db
from vigil.retrieve import TfidfRetriever, build_corpus, load_retriever

CORPUS = [
    {"source_title": "Refund & Return Policy", "source_url": "u/refund", "chunk_index": 0,
     "content": "You can request a full refund of your aligner plan before your aligners are manufactured."},
    {"source_title": "Shipping & Tracking", "source_url": "u/ship", "chunk_index": 0,
     "content": "Your impression kit ships within 1-2 business days and arrives in 3-5 business days with a tracking link."},
    {"source_title": "How Treatment Works", "source_url": "u/how", "chunk_index": 0,
     "content": "Mild soreness for the first few days of a new step is normal and eases within 2-3 days."},
]


def test_tfidf_returns_relevant_chunk():
    r = TfidfRetriever().fit(CORPUS)
    hits = r.search("how do I get a refund for my aligners", k=1)
    assert hits
    assert hits[0].source_title == "Refund & Return Policy"
    assert hits[0].score > 0
    # citation metadata is carried through
    assert hits[0].source_url == "u/refund"


def test_tfidf_tracking_query():
    r = TfidfRetriever().fit(CORPUS)
    hits = r.search("where is my package tracking", k=1)
    assert hits[0].source_title == "Shipping & Tracking"


def test_empty_corpus_returns_nothing():
    r = TfidfRetriever().fit([])
    assert r.search("anything", k=3) == []


def test_build_and_load_roundtrip(tmp_path):
    conn = db.init_db(tmp_path / "t.db")
    # write the 3 corpus rows to a temp file each
    import json
    files = []
    for i, c in enumerate(CORPUS):
        p = tmp_path / f"c{i}.json"
        p.write_text(json.dumps({"source_title": c["source_title"], "source_url": c["source_url"], "chunks": [c["content"]]}))
        files.append(p)
    n = build_corpus(conn, files)
    assert n == 3
    r = load_retriever(conn)
    hits = r.search("refund before manufacturing", k=1)
    assert hits[0].source_title == "Refund & Return Policy"
