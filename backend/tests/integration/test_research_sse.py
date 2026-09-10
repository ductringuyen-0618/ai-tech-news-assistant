"""
Integration tests for the Agentic Research SSE route (M2)
=========================================================

Covers the validation contract from
``docs/issues/agentic-research-2-sse-endpoint.md``:

1. ``test_sse_frame_shape`` -- POST returns ``text/event-stream`` and each
   ``data:`` frame is a discrete ``data: <json>\\n\\n`` block whose
   payload matches the AgentEvent shape; the terminal ``done`` event
   preserves its ``report`` key end-to-end.
2. ``test_token_streaming_emits_token_phase`` -- while synthesis is
   streaming, the client sees multiple ``type: "token"`` events before
   the final ``phase: "done"`` event.
3. ``test_keepalive_emitted_on_slow_event`` -- when no real event has
   been pending for the keepalive interval, a ``: keepalive\\n\\n``
   comment frame appears in the stream.
4. ``test_disconnect_cancels_inflight_generation`` -- when the client
   disconnects mid-run, the SSE generator's cancel/finally handler runs
   and the stub agent's ``except CancelledError`` branch fires.
5. ``test_second_concurrent_post_returns_429`` -- a second POST while
   one run is in flight returns HTTP 429 with the documented body.
6. ``test_inflight_gate_releases_on_completion`` -- after a normal run,
   the gate is released so a second POST succeeds.

Ollama is fully mocked: tests inject a fake agent service via a module-
level ``_build_service`` patch, so no live model is required.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, AsyncGenerator, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import research as research_route


# ---------------------------------------------------------------------- #
#  Helpers
# ---------------------------------------------------------------------- #


def _build_app() -> FastAPI:
    """Build a fresh FastAPI app mounting just the research router."""
    app = FastAPI()
    app.include_router(research_route.router, prefix="/api")
    return app


@pytest.fixture(autouse=True)
def _reset_inflight_gate():
    """Reset the single-in-flight gate before/after every test."""
    research_route._in_flight = False
    yield
    research_route._in_flight = False


def _parse_sse_blocks(body: bytes) -> List[bytes]:
    """Split a raw SSE body into discrete frames at ``\\n\\n`` boundaries."""
    blocks = body.split(b"\n\n")
    return [b for b in blocks if b.strip()]


def _data_payloads(blocks: List[bytes]) -> List[Dict[str, Any]]:
    """Extract JSON payloads from ``data:`` frames; ignore comment frames."""
    payloads: List[Dict[str, Any]] = []
    for blk in blocks:
        text = blk.decode("utf-8", "replace").strip()
        if text.startswith("data:"):
            json_text = text[len("data:"):].strip()
            try:
                payloads.append(json.loads(json_text))
            except json.JSONDecodeError:
                continue
    return payloads


class _StubAgent:
    """A fake :class:`AgenticResearchService` that yields canned events."""

    def __init__(
        self,
        events: List[Dict[str, Any]],
        *,
        per_event_delay: float = 0.0,
        on_cancel: Any = None,
    ):
        self._events = list(events)
        self._delay = per_event_delay
        self._on_cancel = on_cancel
        self.cancelled = False
        self.finally_ran = False

    async def run(self, question: str) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            for evt in self._events:
                if self._delay:
                    await asyncio.sleep(self._delay)
                yield evt
        except asyncio.CancelledError:
            self.cancelled = True
            if callable(self._on_cancel):
                self._on_cancel()
            raise
        except GeneratorExit:
            # ``aclose()`` raises GeneratorExit inside the generator;
            # treat it as a cancellation signal too so disconnect tests
            # can observe cleanup either way.
            self.cancelled = True
            if callable(self._on_cancel):
                self._on_cancel()
            raise
        finally:
            self.finally_ran = True


# ---------------------------------------------------------------------- #
#  Tests
# ---------------------------------------------------------------------- #


def test_sse_frame_shape(monkeypatch):
    """POST /api/research returns text/event-stream and well-shaped frames."""
    stub = _StubAgent(
        events=[
            {"type": "phase", "data": "Decomposing"},
            {"type": "phase", "data": "Searching (1/2)"},
            {"type": "phase", "data": "Synthesizing"},
            {"type": "token", "data": "## Summary\nHello "},
            {"type": "token", "data": "world.\n"},
            {
                "type": "phase",
                "data": "done",
                "report": "## Summary\nHello world.\n[1] x -- y (z)\n",
            },
        ]
    )
    monkeypatch.setattr(research_route, "_build_service", lambda: stub)

    app = _build_app()
    client = TestClient(app)
    with client.stream(
        "POST", "/api/research", json={"question": "anything"}
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = b"".join(resp.iter_bytes())

    blocks = _parse_sse_blocks(body)
    payloads = _data_payloads(blocks)

    assert [p["type"] for p in payloads] == [
        "phase", "phase", "phase", "token", "token", "phase",
    ]
    assert payloads[-1]["data"] == "done"
    assert "report" in payloads[-1]
    assert "[1]" in payloads[-1]["report"]

    for blk in blocks:
        text = blk.decode("utf-8", "replace")
        assert text.startswith("data:") or text.startswith(":"), text


def test_token_streaming_emits_token_phase(monkeypatch):
    """Multiple ``type: "token"`` events arrive before the terminal done."""
    stub = _StubAgent(
        events=[
            {"type": "phase", "data": "Synthesizing"},
            {"type": "token", "data": "alpha "},
            {"type": "token", "data": "beta "},
            {"type": "token", "data": "gamma"},
            {
                "type": "phase",
                "data": "done",
                "report": "alpha beta gamma\n[1] s\n",
            },
        ]
    )
    monkeypatch.setattr(research_route, "_build_service", lambda: stub)

    app = _build_app()
    client = TestClient(app)
    with client.stream(
        "POST", "/api/research", json={"question": "stream me"}
    ) as resp:
        body = b"".join(resp.iter_bytes())

    payloads = _data_payloads(_parse_sse_blocks(body))
    token_events = [p for p in payloads if p["type"] == "token"]
    assert len(token_events) >= 2, payloads
    last_idx = next(
        i for i, p in enumerate(payloads)
        if p["type"] == "phase" and p.get("data") == "done"
    )
    token_indices = [
        i for i, p in enumerate(payloads) if p["type"] == "token"
    ]
    assert all(i < last_idx for i in token_indices)


def test_keepalive_emitted_on_slow_event(monkeypatch):
    """A ``: keepalive\\n\\n`` comment frame appears when no event arrives."""
    stub = _StubAgent(
        events=[
            {"type": "phase", "data": "Decomposing"},
            {
                "type": "phase",
                "data": "done",
                "report": "ok\n[1] s\n",
            },
        ],
        per_event_delay=0.2,
    )
    monkeypatch.setattr(research_route, "_build_service", lambda: stub)
    monkeypatch.setattr(
        research_route, "KEEPALIVE_INTERVAL_SECONDS", 0.05
    )

    app = _build_app()
    client = TestClient(app)
    with client.stream(
        "POST", "/api/research", json={"question": "slow"}
    ) as resp:
        body = b"".join(resp.iter_bytes())

    assert b": keepalive\n\n" in body, body[:500]
    payloads = _data_payloads(_parse_sse_blocks(body))
    assert any(p["type"] == "phase" and p.get("data") == "done" for p in payloads)


def test_disconnect_cancels_inflight_generation():
    """Disconnect mid-run runs the agent's cancel/cleanup handler.

    We drive ``_stream_research`` directly with a fake Request that
    flips ``is_disconnected -> True`` after the first event arrives.
    This exercises the same finally / cancel logic that fires in
    production when a client closes the SSE connection, without
    depending on a real ASGI transport's TCP-close semantics.
    """
    cancel_observed = threading.Event()

    def _on_cancel():
        cancel_observed.set()

    stub = _StubAgent(
        events=[
            {"type": "phase", "data": "Decomposing"},
            {"type": "phase", "data": "Searching (1/1)"},
            {"type": "phase", "data": "Synthesizing"},
            *[{"type": "token", "data": "tk "} for _ in range(50)],
            {"type": "phase", "data": "done", "report": "ok\n[1] s\n"},
        ],
        per_event_delay=0.05,
        on_cancel=_on_cancel,
    )

    class _FakeRequest:
        """Minimal Request stand-in: flips disconnected after N polls."""

        def __init__(self, flip_after: int = 1):
            self._polls = 0
            self._flip_after = flip_after

        async def is_disconnected(self) -> bool:
            self._polls += 1
            return self._polls > self._flip_after

    async def _drive() -> None:
        agen = stub.run("dummy")
        req = _FakeRequest(flip_after=1)
        # Iterate a few frames then expect the generator to short-circuit
        # because is_disconnected returns True on its second poll.
        out = research_route._stream_research(req, agen)
        try:
            count = 0
            async for _frame in out:
                count += 1
                if count > 100:  # safety
                    break
        finally:
            await out.aclose()
        # Allow the scheduled cancellation to settle.
        for _ in range(20):
            if stub.cancelled or cancel_observed.is_set():
                return
            await asyncio.sleep(0.05)

    asyncio.run(_drive())

    assert stub.cancelled or cancel_observed.is_set(), (
        "expected agent generator to receive CancelledError / GeneratorExit "
        "on simulated disconnect"
    )
    assert stub.finally_ran, "agent generator finally block should always run"


def test_second_concurrent_post_returns_429(monkeypatch):
    """A second POST while a run is in flight returns HTTP 429."""
    monkeypatch.setattr(
        research_route, "_build_service",
        lambda: _StubAgent(events=[]),
    )

    research_route._in_flight = True

    app = _build_app()
    client = TestClient(app)
    resp = client.post("/api/research", json={"question": "second"})
    assert resp.status_code == 429
    body = resp.json()
    assert body == {"detail": "Another research run is in flight"}


def test_inflight_gate_releases_on_completion(monkeypatch):
    """After a run completes, the gate is released so the next POST works."""
    stub = _StubAgent(
        events=[
            {"type": "phase", "data": "done", "report": "x\n[1] y\n"},
        ]
    )
    monkeypatch.setattr(research_route, "_build_service", lambda: stub)

    app = _build_app()
    client = TestClient(app)
    with client.stream(
        "POST", "/api/research", json={"question": "one"}
    ) as resp:
        b"".join(resp.iter_bytes())

    assert research_route._in_flight is False
    with client.stream(
        "POST", "/api/research", json={"question": "two"}
    ) as resp:
        assert resp.status_code == 200


# ---------------------------------------------------------------------- #
#  M3.M2 — Three additive event types: decomposed, search_results,
#  subagent:done with `summary` field. Backward compatible with the 6
#  existing tests above.
# ---------------------------------------------------------------------- #


def test_decomposed_event_emitted(monkeypatch):
    """A ``decomposed`` event MUST arrive with the sub-questions list.

    The new event allows the frontend to render the sub-questions panel
    within ~5s of submit (before any synthesis tokens). It's ADDITIVE —
    existing phase events still fire in the same sequence.
    """
    stub = _StubAgent(
        events=[
            {"type": "phase", "data": "Decomposing"},
            {
                "type": "decomposed",
                "sub_questions": [
                    "What companies are involved?",
                    "How does the new chip compare?",
                    "What's the funding situation?",
                ],
            },
            {"type": "phase", "data": "Searching (1/3)"},
            {"type": "phase", "data": "Synthesizing"},
            {"type": "token", "data": "## Summary\n"},
            {
                "type": "phase",
                "data": "done",
                "report": "## Summary\n[1] x\n",
            },
        ]
    )
    monkeypatch.setattr(research_route, "_build_service", lambda: stub)

    app = _build_app()
    client = TestClient(app)
    with client.stream(
        "POST", "/api/research", json={"question": "anything"}
    ) as resp:
        assert resp.status_code == 200
        body = b"".join(resp.iter_bytes())

    payloads = _data_payloads(_parse_sse_blocks(body))
    decomposed = [p for p in payloads if p.get("type") == "decomposed"]
    assert len(decomposed) == 1, payloads
    assert isinstance(decomposed[0].get("sub_questions"), list)
    assert len(decomposed[0]["sub_questions"]) == 3
    assert all(isinstance(q, str) for q in decomposed[0]["sub_questions"])

    # Decomposed event MUST arrive BEFORE any Searching phase event so
    # the frontend can pre-render the sub-question slots.
    decomposed_idx = next(
        i for i, p in enumerate(payloads) if p.get("type") == "decomposed"
    )
    searching_indices = [
        i for i, p in enumerate(payloads)
        if p.get("type") == "phase"
        and isinstance(p.get("data"), str)
        and p["data"].startswith("Searching")
    ]
    assert searching_indices, "expected at least one Searching phase event"
    assert decomposed_idx < min(searching_indices), (
        "decomposed event must arrive before the first Searching phase event"
    )


def test_search_results_event_per_sub_question(monkeypatch):
    """One ``search_results`` event MUST arrive per sub-question.

    Each event names the sub-question index (0-based) and an articles
    list of ``{id, title, source}`` previews. Body / snippet are NOT
    included — those keep the frame small.
    """
    stub = _StubAgent(
        events=[
            {"type": "phase", "data": "Decomposing"},
            {
                "type": "decomposed",
                "sub_questions": ["q1", "q2"],
            },
            {"type": "phase", "data": "Searching (1/2)"},
            {
                "type": "search_results",
                "sub_question_index": 0,
                "articles": [
                    {"id": 42, "title": "Article 42", "source": "TechCrunch"},
                    {"id": 17, "title": "Article 17", "source": "ArsTechnica"},
                ],
            },
            {"type": "phase", "data": "Searching (2/2)"},
            {
                "type": "search_results",
                "sub_question_index": 1,
                "articles": [
                    {"id": 99, "title": "Article 99", "source": "Wired"},
                ],
            },
            {"type": "phase", "data": "Synthesizing"},
            {
                "type": "phase",
                "data": "done",
                "report": "## Summary\n[1] x\n",
            },
        ]
    )
    monkeypatch.setattr(research_route, "_build_service", lambda: stub)

    app = _build_app()
    client = TestClient(app)
    with client.stream(
        "POST", "/api/research", json={"question": "anything"}
    ) as resp:
        body = b"".join(resp.iter_bytes())

    payloads = _data_payloads(_parse_sse_blocks(body))
    sr = [p for p in payloads if p.get("type") == "search_results"]
    assert len(sr) == 2, payloads
    # Indices are 0-based.
    assert {e.get("sub_question_index") for e in sr} == {0, 1}

    for e in sr:
        articles = e.get("articles")
        assert isinstance(articles, list)
        for a in articles:
            assert set(a.keys()) >= {"id", "title", "source"}, a
            # Body / snippet keys MUST be absent from the SSE frame.
            assert "body" not in a
            assert "snippet" not in a
            assert "summary" not in a


def test_subagent_done_includes_summary_field(monkeypatch):
    """Each ``subagent: done`` event MUST include a ``summary`` field.

    The summary is the first 280 chars of the per-article summary; the
    frontend uses it for the expandable-row preview. Other subagent
    lifecycle fields (skill, article_id, duration_ms) are preserved.
    """
    stub = _StubAgent(
        events=[
            {
                "type": "subagent",
                "data": "start",
                "skill": "summarize_article",
                "article_id": 42,
            },
            {
                "type": "subagent",
                "data": "done",
                "skill": "summarize_article",
                "article_id": 42,
                "duration_ms": 1234,
                "summary": "The article describes a new AI chip launch. "
                "Pricing pressure across tier-1 vendors. "
                "Edge-deployment focus growing. " * 2,
            },
            {
                "type": "phase",
                "data": "done",
                "report": "x\n[1] y\n",
            },
        ]
    )
    monkeypatch.setattr(research_route, "_build_service", lambda: stub)

    app = _build_app()
    client = TestClient(app)
    with client.stream(
        "POST", "/api/research", json={"question": "anything"}
    ) as resp:
        body = b"".join(resp.iter_bytes())

    payloads = _data_payloads(_parse_sse_blocks(body))
    dones = [
        p
        for p in payloads
        if p.get("type") == "subagent" and p.get("data") == "done"
    ]
    assert len(dones) == 1, payloads
    done = dones[0]
    # The new field MUST be present.
    assert "summary" in done, done
    assert isinstance(done["summary"], str)
    assert len(done["summary"]) > 0
    # Existing fields preserved (backward compat).
    assert done.get("skill") == "summarize_article"
    assert done.get("article_id") == 42
    assert done.get("duration_ms") == 1234
