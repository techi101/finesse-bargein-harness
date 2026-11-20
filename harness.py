"""Turn-taking measurements for a realtime TTS client, driven through the real flam-finesse SDK.

Two things are measured from the listener's side (what a speaker or a lip-sync renderer
would get), not from the socket:

1. Time to first audio (TTFA) for a turn whose text arrives token by token from an LLM.
2. Barge-in: after ``ctx.cancel()`` returns, how many seconds of this turn's speech a player
   that follows the SDK README pattern still receives and plays.

The player plays in real time: it "plays" a chunk by sleeping for that chunk's duration,
the same back-pressure a blocking ``speaker.write(pcm)`` creates.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from typing import AsyncIterator, List, Optional, Sequence, Tuple

from flam_finesse import AsyncFinesse, AudioEvent, RealtimeEvent, TaskCancelled

BYTES_PER_SECOND = 24000 * 2  # s16le mono at the native 24 kHz
VOICE_ID = "0" * 24  # any 24-hex id; the mock accepts every voice


def audio_seconds(pcm: bytes) -> float:
    return len(pcm) / BYTES_PER_SECOND


# ---- the fix ---------------------------------------------------------------------------------


class Interruptible:
    """Wrap a context so a barge-in silences it at once. Public SDK API only.

    Two gaps in flam-finesse 0.1.1 that this covers (see README):

    * ``cancel()`` drops audio that *arrives* after it, but audio that already arrived sits in
      the context's unbounded queue and is still yielded by ``async for event in ctx``.
    * If the server already sent ``task_done`` (fast synthesis, short turn), ``cancel()``
      returns early without setting ``ctx.cancelled``, so the whole buffered turn still plays.

    ``interrupt()`` keeps its own flag, so neither case leaks audio. Iteration keeps reading
    to the end of the turn, so a cancelled turn still ends on ``TaskCancelled``."""

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.interrupted = False

    async def interrupt(self) -> None:
        self.interrupted = True
        await self.ctx.cancel()

    async def __aiter__(self) -> AsyncIterator[RealtimeEvent]:
        async for event in self.ctx:
            if self.interrupted and isinstance(event, AudioEvent):
                continue
            yield event


# ---- barge-in ----------------------------------------------------------------------------------


@dataclass
class BargeInResult:
    mode: str  # "sdk_pattern" or "interruptible"
    speed: float  # mock generation speed (x realtime)
    barge_in_after_s: float  # seconds of speech played before the user talks over it
    stale_audio_s: float  # speech the player still got after cancel() returned
    silence_latency_ms: float  # cancel() returned -> the player's last chunk finished playing
    turn_end_ms: float  # cancel() returned -> the context iterator ended
    ended_with_cancelled: bool
    server_done_before_cancel: bool  # task_done had already arrived when the user barged in


async def barge_in_turn(base_url: str, text: str, barge_in_after_s: float,
                        use_fix: bool, speed: float = 0.0) -> BargeInResult:
    client = AsyncFinesse(api_key="flv_offline_mock", base_url=base_url, max_retries=0)
    played = 0.0
    stale = 0.0
    cancel_done: Optional[float] = None
    last_play_end: Optional[float] = None
    ended_cancelled = False
    server_done_before_cancel = False
    async with client.realtime.connect() as rt:
        ctx = rt.context(voice_id=VOICE_ID)
        await ctx.send(text, finalize=True)
        wrapped = Interruptible(ctx)
        events = wrapped if use_fix else ctx
        async for event in events:
            if isinstance(event, TaskCancelled):
                ended_cancelled = True
            if not isinstance(event, AudioEvent):
                continue
            dur = audio_seconds(event.pcm)
            if cancel_done is not None:
                stale += dur
            await asyncio.sleep(dur)  # real-time playback, like a blocking speaker.write
            played += dur
            last_play_end = time.perf_counter()
            if cancel_done is None and played >= barge_in_after_s - 1e-9:
                server_done_before_cancel = ctx._ended  # private; read only for the report
                # The user started talking.
                await (wrapped.interrupt() if use_fix else ctx.cancel())
                cancel_done = time.perf_counter()
        turn_end = time.perf_counter()
    await client.close()
    assert cancel_done is not None, "turn ended before the barge-in point"
    silence = max(0.0, (last_play_end or cancel_done) - cancel_done)
    return BargeInResult(
        mode="interruptible" if use_fix else "sdk_pattern",
        speed=speed,
        barge_in_after_s=barge_in_after_s,
        stale_audio_s=round(stale, 3),
        silence_latency_ms=round(silence * 1000, 1),
        turn_end_ms=round((turn_end - cancel_done) * 1000, 1),
        ended_with_cancelled=ended_cancelled,
        server_done_before_cancel=server_done_before_cancel,
    )


# ---- time to first audio --------------------------------------------------------------------


@dataclass
class TTFAResult:
    scenario: str
    idle_flush_ms: Optional[int]
    ttfa_ms: float  # first text sent -> first audio chunk yielded
    budget_ms: float
    within_budget: bool


async def ttfa_turn(base_url: str, scenario: str, pieces: Sequence[Tuple[str, float]],
                    idle_flush_ms: Optional[int] = None, budget_ms: float = 800.0) -> TTFAResult:
    """``pieces`` is the LLM stream: (text, seconds to wait before sending it)."""
    client = AsyncFinesse(api_key="flv_offline_mock", base_url=base_url, max_retries=0)
    first_audio: List[float] = []
    async with client.realtime.connect() as rt:
        ctx = rt.context(voice_id=VOICE_ID, idle_flush_ms=idle_flush_ms)

        async def listen() -> None:
            async for event in ctx:
                if isinstance(event, AudioEvent) and not first_audio:
                    first_audio.append(time.perf_counter())

        t0 = time.perf_counter()
        listener = None
        for i, (text, wait) in enumerate(pieces):
            if wait:
                await asyncio.sleep(wait)
            if i == 0:
                t0 = time.perf_counter()
            await ctx.send(text)
            if listener is None:
                listener = asyncio.create_task(listen())
        await ctx.finish()
        await listener
    await client.close()
    ttfa = (first_audio[0] - t0) * 1000
    return TTFAResult(scenario, idle_flush_ms, round(ttfa, 1), budget_ms, ttfa <= budget_ms)


def as_dict(result) -> dict:
    return asdict(result)
