"""A small local stand-in for the Finesse realtime WebSocket (finesse.v1).

It is NOT Flam's server. It speaks the message shapes that the public Python SDK
(flam-finesse 0.1.1, src/flam_finesse/realtime.py) sends and parses, so the real SDK can
connect to it offline:

    client -> server: task_start, task_continue (text, finalize), task_cancel, session_end
    server -> client: task_started, audio_chunk (JSON header) + one binary PCM frame,
                      sentence_done, task_done, task_cancelled

Timing is synthetic and set by MockConfig, so every number this mock produces is a
property of the config, not a measurement of Finesse. What the mock is good for is
driving the real client code through realistic timing shapes (audio generated faster
than realtime, an LLM that pauses mid-sentence, a cancel mid-turn).
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

PATH = "/flam-voice-svc/api/v1/public/stream"  # API_PREFIX + "/stream" in the SDK
SAMPLE_RATE = 24000  # native rate per the SDK README
BYTES_PER_SECOND = SAMPLE_RATE * 2  # s16le mono

_SENTENCE_END = re.compile(r"[.!?](\s|$)")


@dataclass
class MockConfig:
    sentence_latency_ms: float = 150.0  # wait before a sentence's first chunk
    speed: float = 4.0  # audio generated per wall second (4.0 = 4x faster than realtime)
    chunk_ms: float = 100.0  # audio per chunk
    ms_per_char: float = 65.0  # speech length model (about 15 characters per second)
    idle_flush_ms: float = 800.0  # default when the client sends none (pipecat-finesse docstring)


@dataclass
class _Context:
    cid: str
    idle_flush_ms: float
    buffer: str = ""
    finalized: bool = False
    cancelled: bool = False
    sentences: "asyncio.Queue[Optional[str]]" = field(default_factory=asyncio.Queue)
    completed: int = 0
    queued: int = 0
    worker: Optional[asyncio.Task] = None
    idle_timer: Optional[asyncio.Task] = None


class FinesseMock:
    """Run with ``async with FinesseMock(cfg) as mock:``; ``mock.base_url`` goes to the SDK."""

    def __init__(self, config: Optional[MockConfig] = None) -> None:
        self.config = config or MockConfig()
        self.base_url = ""
        self.received: List[Dict[str, Any]] = []  # every client JSON message, for tests
        self._server = None

    async def __aenter__(self) -> "FinesseMock":
        self._server = await serve(self._handle, "127.0.0.1", 0, compression=None)
        port = self._server.sockets[0].getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        return self

    async def __aexit__(self, *exc: Any) -> None:
        self._server.close()
        await self._server.wait_closed()

    # ---- connection ----------------------------------------------------------

    async def _handle(self, ws: ServerConnection) -> None:
        if ws.request.path != PATH or not ws.request.headers.get("X-API-Key"):
            await ws.close(1008, "unauthorized")
            return
        send_lock = asyncio.Lock()  # an audio header and its binary frame must stay adjacent
        contexts: Dict[str, _Context] = {}
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    continue
                msg = json.loads(raw)
                self.received.append(msg)
                kind = msg.get("type")
                if kind == "session_end":
                    break
                cid = msg.get("context_id")
                if kind == "task_start":
                    ctx = _Context(cid, float(msg.get("idle_flush_ms") or self.config.idle_flush_ms))
                    contexts[cid] = ctx
                    await self._send(ws, send_lock, {
                        "type": "task_started", "context_id": cid,
                        "sample_rate": SAMPLE_RATE, "audio_format": "s16le",
                    })
                    ctx.worker = asyncio.create_task(self._synthesize(ws, send_lock, ctx))
                    self._add_text(ctx, msg.get("text") or "", bool(msg.get("finalize")))
                elif kind == "task_continue" and cid in contexts:
                    self._add_text(contexts[cid], msg.get("text") or "", bool(msg.get("finalize")))
                elif kind == "task_cancel" and cid in contexts:
                    await self._cancel(ws, send_lock, contexts.pop(cid))
        except ConnectionClosed:
            pass
        finally:
            for ctx in contexts.values():
                for t in (ctx.worker, ctx.idle_timer):
                    if t:
                        t.cancel()
        await ws.close(1000)

    async def _send(self, ws: ServerConnection, lock: asyncio.Lock, msg: Dict[str, Any],
                    audio: Optional[bytes] = None) -> None:
        async with lock:
            await ws.send(json.dumps(msg))
            if audio is not None:
                await ws.send(audio)

    # ---- text -> sentences ---------------------------------------------------

    def _add_text(self, ctx: _Context, text: str, finalize: bool) -> None:
        if ctx.cancelled or ctx.finalized:
            return
        ctx.buffer += text
        while True:  # complete sentences go to synthesis at once
            m = _SENTENCE_END.search(ctx.buffer)
            if not m:
                break
            self._enqueue(ctx, ctx.buffer[: m.end()])
            ctx.buffer = ctx.buffer[m.end():]
        if ctx.idle_timer:
            ctx.idle_timer.cancel()
            ctx.idle_timer = None
        if finalize:
            ctx.finalized = True
            if ctx.buffer.strip():
                self._enqueue(ctx, ctx.buffer)
            ctx.buffer = ""
            ctx.sentences.put_nowait(None)  # end marker
        elif ctx.buffer.strip():
            ctx.idle_timer = asyncio.create_task(self._idle_flush(ctx))

    def _enqueue(self, ctx: _Context, sentence: str) -> None:
        if sentence.strip():
            ctx.queued += 1
            ctx.sentences.put_nowait(sentence.strip())

    async def _idle_flush(self, ctx: _Context) -> None:
        # Modeled on the SDK docstring: "Speak a pending sentence after this many ms without new text."
        await asyncio.sleep(ctx.idle_flush_ms / 1000)
        if ctx.buffer.strip() and not ctx.cancelled:
            self._enqueue(ctx, ctx.buffer)
            ctx.buffer = ""

    # ---- synthesis -----------------------------------------------------------

    async def _synthesize(self, ws: ServerConnection, lock: asyncio.Lock, ctx: _Context) -> None:
        cfg = self.config
        sentence_index = 0
        total_audio = 0.0
        try:
            while True:
                sentence = await ctx.sentences.get()
                if sentence is None:
                    break
                await asyncio.sleep(cfg.sentence_latency_ms / 1000)
                audio_s = len(sentence) * cfg.ms_per_char / 1000
                n_chunks = max(1, round(audio_s * 1000 / cfg.chunk_ms))
                chunk_bytes = int(BYTES_PER_SECOND * cfg.chunk_ms / 1000)
                for i in range(n_chunks):
                    if i:  # chunk i is ready chunk_ms/speed after chunk i-1
                        await asyncio.sleep(cfg.chunk_ms / 1000 / cfg.speed)
                    pcm = bytes([sentence_index % 256, i % 256]) * (chunk_bytes // 2)
                    await self._send(ws, lock, {
                        "type": "audio_chunk", "context_id": ctx.cid,
                        "sentence_index": sentence_index, "chunk_index": i,
                        "audio_duration_s": cfg.chunk_ms / 1000,
                    }, audio=pcm)
                total_audio += n_chunks * cfg.chunk_ms / 1000
                ctx.completed += 1
                await self._send(ws, lock, {
                    "type": "sentence_done", "context_id": ctx.cid,
                    "sentence_index": sentence_index, "text": sentence,
                    "audio_duration_s": n_chunks * cfg.chunk_ms / 1000,
                })
                sentence_index += 1
            await self._send(ws, lock, {
                "type": "task_done", "context_id": ctx.cid,
                "num_sentences": sentence_index, "total_audio_duration_s": round(total_audio, 3),
            })
        except (asyncio.CancelledError, ConnectionClosed):
            pass

    async def _cancel(self, ws: ServerConnection, lock: asyncio.Lock, ctx: _Context) -> None:
        ctx.cancelled = True
        for t in (ctx.worker, ctx.idle_timer):
            if t:
                t.cancel()
        await self._send(ws, lock, {
            "type": "task_cancelled", "context_id": ctx.cid,
            "sentences_completed": ctx.completed,
            "sentences_dropped": max(0, ctx.queued - ctx.completed),
        })
