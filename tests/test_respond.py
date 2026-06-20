"""Reply storage round-trip and lane gating (only non-clinical lanes get a draft). Fake client."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from vigil import db
from vigil.respond import ensure_reply, get_reply, store_reply
from vigil.retrieve import RetrievedChunk
from vigil.schemas import GroundedReply, Message


def _client():
    def create(**kwargs):
        block = SimpleNamespace(
            type="tool_use", id="r",
            input={"body": "Your kit ships in 1-2 business days.", "answerable": True},
        )
        return SimpleNamespace(content=[block], stop_reason="tool_use")

    return SimpleNamespace(messages=SimpleNamespace(create=MagicMock(side_effect=create)))


def _seed_message(conn, mid="m1", text="where is my kit"):
    conn.execute("INSERT INTO messages (id, raw_text, journey_stage) VALUES (?, ?, ?)", (mid, text, "pre_kit"))
    conn.commit()


def test_store_get_roundtrip(tmp_path):
    conn = db.init_db(tmp_path / "t.db")
    _seed_message(conn)
    store_reply(conn, "m1", GroundedReply(body="hello", source_title="Shipping", source_url="u", grounded=True))
    r = get_reply(conn, "m1")
    assert r is not None and r.body == "hello" and r.grounded is True


def test_ensure_reply_gates_clinical_and_caches(tmp_path):
    conn = db.init_db(tmp_path / "t.db")
    _seed_message(conn)
    client = _client()
    msg = Message(id="m1", raw_text="where is my kit", journey_stage="pre_kit")
    chunk = RetrievedChunk(content="Your kit ships in 1-2 days.", source_title="Shipping", source_url="u", chunk_index=0, score=0.5)

    # Clinical lane -> NO reply, no model call.
    assert ensure_reply(conn, client, msg, "clinical_review", chunk) is None
    assert client.messages.create.call_count == 0

    # auto_send -> reply generated, grounded, with the human-gate caption.
    reply = ensure_reply(conn, client, msg, "auto_send", chunk)
    assert reply is not None and reply.grounded is True
    assert "pending human review" in reply.body
    assert client.messages.create.call_count == 1

    # Cached by existence -> no second model call.
    ensure_reply(conn, client, msg, "auto_send", chunk)
    assert client.messages.create.call_count == 1


def test_held_lane_deletes_stale_reply(tmp_path):
    # A reply left over from a prior run must be removed if the message now routes to a held lane.
    conn = db.init_db(tmp_path / "t.db")
    _seed_message(conn)
    store_reply(conn, "m1", GroundedReply(body="old draft", grounded=True))
    assert get_reply(conn, "m1") is not None

    msg = Message(id="m1", raw_text="now a clinical case", journey_stage="in_treatment")
    client = _client()
    result = ensure_reply(conn, client, msg, "vigilance_review", None)
    assert result is None
    assert get_reply(conn, "m1") is None  # stale reply purged
    assert client.messages.create.call_count == 0
