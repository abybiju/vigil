"""Safe-lane grounded reply: rules decide eligibility, the LLM only phrases.

The reply is grounded ONLY on the retrieved FAQ chunk and cites it. Refund/journey
eligibility comes from rules.py (never the model). Every draft carries the human-gate caption.
Replies are stored per message so the UI never makes a model call in its render path.
"""

from __future__ import annotations

import anthropic
from pydantic import BaseModel

from . import config, db
from .llm import structured_call
from .retrieve import RetrievedChunk
from .rules import refund_eligibility
from .schemas import GroundedReply, Message

# Lanes that may receive an auto/agent-drafted reply. Clinical/vigilance lanes are held.
REPLYABLE_LANES = {"auto_send", "agent_draft"}


class _ReplyDraft(BaseModel):
    body: str
    answerable: bool


REPLY_SYSTEM = """You draft customer-support replies for a clear-aligner brand. STRICT RULES:
- Ground your answer ONLY in the SOURCE text provided. Do not use outside knowledge or invent policy.
- If the SOURCE does not actually answer the customer, set answerable=false and write a short, warm \
message saying a support agent will follow up — do NOT guess.
- If REFUND ELIGIBILITY is provided, state it exactly as given; never decide eligibility yourself.
- Never give clinical or medical advice. If the message contains any health concern, do not answer it \
here.
- Keep it concise, friendly, and professional. Do not include a signature or placeholder names.
Return the reply via the tool."""


def generate_reply(
    client: anthropic.Anthropic,
    message: Message,
    top_chunk: RetrievedChunk | None,
    *,
    model: str | None = None,
) -> GroundedReply:
    refund = refund_eligibility(message.journey_stage)
    source_text = top_chunk.content if top_chunk else "(no source retrieved)"

    user = (
        f'CUSTOMER MESSAGE:\n"""\n{message.raw_text}\n"""\n\n'
        f"SOURCE (the only allowed basis for facts):\n{source_text}\n\n"
        f"REFUND ELIGIBILITY (state exactly if relevant): tier={refund.tier}, "
        f"eligible={refund.eligible} — {refund.reason}"
    )
    draft = structured_call(
        client,
        model=model or config.TRIAGE_MODEL,
        system=REPLY_SYSTEM,
        user=user,
        schema_model=_ReplyDraft,
        tool_name="draft_reply",
        max_tokens=512,
    )

    grounded = bool(draft.answerable and top_chunk is not None)
    body = f"{draft.body}\n\n— {config.HUMAN_GATE_CAPTION}"
    return GroundedReply(
        body=body,
        source_title=top_chunk.source_title if grounded else None,
        source_url=top_chunk.source_url if grounded else None,
        grounded=grounded,
    )


def store_reply(conn, message_id: str, reply: GroundedReply) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO replies (message_id, body, source_title, source_url, grounded, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, reply.body, reply.source_title, reply.source_url, 1 if reply.grounded else 0, db.now_iso()),
    )
    conn.commit()


def get_reply(conn, message_id: str) -> GroundedReply | None:
    row = db.query_one(conn, "SELECT * FROM replies WHERE message_id = ?", (message_id,))
    if row is None:
        return None
    return GroundedReply(
        body=row["body"],
        source_title=row["source_title"],
        source_url=row["source_url"],
        grounded=bool(row["grounded"]),
    )


def ensure_reply(
    conn,
    client: anthropic.Anthropic,
    message: Message,
    routing_decision: str,
    top_chunk: RetrievedChunk | None,
    *,
    no_cache: bool = False,
) -> GroundedReply | None:
    """Generate + store a reply for reply-eligible lanes only. Cached by existence (free re-runs).

    A held lane (clinical/vigilance) actively deletes any stale reply left over from a prior run in
    which the message routed differently — a held case must never carry a draft.
    """
    if routing_decision not in REPLYABLE_LANES:
        conn.execute("DELETE FROM replies WHERE message_id = ?", (message.id,))
        conn.commit()
        return None
    if not no_cache:
        existing = get_reply(conn, message.id)
        if existing is not None:
            return existing
    reply = generate_reply(client, message, top_chunk)
    store_reply(conn, message.id, reply)
    return reply
