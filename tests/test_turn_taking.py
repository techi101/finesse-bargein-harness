"""Tests run the real flam-finesse SDK against the local mock. Offline, CPU only."""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from flam_finesse import AsyncFinesse, AudioEvent, SentenceDone, TaskCancelled, TaskDone, TaskStarted

from finesse_mock import FinesseMock, MockConfig
from harness import VOICE_ID, Interruptible, audio_seconds, barge_in_turn, ttfa_turn

TURN = "The flat has two bedrooms and a balcony. It gets morning light. Want to visit this weekend?"


def run(coro):
    return asyncio.run(coro)


def client_for(mock):
    return AsyncFinesse(api_key="flv_offline_mock", base_url=mock.base_url, max_retries=0)


# ---- the mock speaks the SDK's protocol -----------------------------------------------------


def test_sdk_say_completes_against_mock():
    async def go():
        async with FinesseMock(MockConfig(speed=50, sentence_latency_ms=5)) as mock:
            client = client_for(mock)
            async with client.realtime.connect() as rt:
                events = [e async for e in rt.say(voice_id=VOICE_ID, text="Hello there. Bye.")]
            await client.close()
            return events, mock.received

    events, received = run(go())
    assert isinstance(events[0], TaskStarted) and events[0].sample_rate == 24000
    assert isinstance(events[-1], TaskDone) and events[-1].num_sentences == 2
    assert sum(isinstance(e, SentenceDone) for e in events) == 2
    audio = sum(audio_seconds(e.pcm) for e in events if isinstance(e, AudioEvent))
    assert abs(audio - events[-1].total_audio_duration_s) < 1e-6
    assert received[0]["type"] == "task_start" and received[0]["voice_id"] == VOICE_ID


def test_mock_rejects_wrong_path():
    async def go():
        async with FinesseMock() as mock:
            from websockets.asyncio.client import connect
            async with connect(mock.base_url.replace("http", "ws") + "/wrong") as ws:
                await ws.wait_closed()
                return ws.close_code

    assert run(go()) == 1008


def test_streamed_tokens_split_into_sentences():
    async def go():
        async with FinesseMock(MockConfig(speed=50, sentence_latency_ms=5)) as mock:
            client = client_for(mock)
            async with client.realtime.connect() as rt:
                ctx = rt.context(voice_id=VOICE_ID)
                for piece in ["Hi", " there.", " How", " are you", "?"]:
                    await ctx.send(piece)
                await ctx.finish()
                done = [e for e in [e async for e in ctx] if isinstance(e, SentenceDone)]
            await client.close()
            return [d.text for d in done]

    assert run(go()) == ["Hi there.", "How are you?"]


# ---- barge-in -----------------------------------------------------------------------------


def test_cancel_mid_turn_ends_with_task_cancelled():
    async def go():
        async with FinesseMock(MockConfig(speed=1, sentence_latency_ms=5)) as mock:
            r = await barge_in_turn(mock.base_url, TURN, barge_in_after_s=0.3, use_fix=False)
            return r, [m["type"] for m in mock.received]

    r, types = run(go())
    assert r.ended_with_cancelled and "task_cancel" in types
    assert r.stale_audio_s < 0.15  # realtime generation leaves (almost) no backlog


def test_sdk_pattern_replays_buffered_audio_after_cancel():
    """Documents the gap: with 4x-realtime generation, the README pattern keeps playing."""
    async def go():
        async with FinesseMock(MockConfig(speed=4)) as mock:
            return await barge_in_turn(mock.base_url, TURN, barge_in_after_s=0.5, use_fix=False)

    r = run(go())
    assert r.stale_audio_s >= 0.5
    assert r.silence_latency_ms >= 500


def test_interruptible_silences_immediately_mid_turn():
    async def go():
        async with FinesseMock(MockConfig(speed=4)) as mock:
            return await barge_in_turn(mock.base_url, TURN, barge_in_after_s=0.5, use_fix=True)

    r = run(go())
    assert r.stale_audio_s == 0.0 and r.silence_latency_ms < 50
    assert r.ended_with_cancelled  # the turn still ends the normal way


def test_cancel_after_task_done_is_a_noop_and_audio_keeps_coming():
    """When the server already finished the turn, cancel() returns early: ctx.cancelled stays
    False, no task_cancel is sent, and every buffered chunk is still yielded."""
    async def go():
        async with FinesseMock(MockConfig(speed=200, sentence_latency_ms=1)) as mock:
            client = client_for(mock)
            async with client.realtime.connect() as rt:
                ctx = rt.context(voice_id=VOICE_ID)
                await ctx.send(TURN, finalize=True)
                await asyncio.sleep(0.5)  # the whole turn arrives and sits in the queue
                await ctx.cancel()
                cancelled_flag = ctx.cancelled
                after = [e async for e in ctx]
            await client.close()
            return cancelled_flag, after, [m["type"] for m in mock.received]

    cancelled_flag, after, types = run(go())
    assert cancelled_flag is False
    assert "task_cancel" not in types
    assert sum(audio_seconds(e.pcm) for e in after if isinstance(e, AudioEvent)) > 5.0
    assert isinstance(after[-1], TaskDone)


def test_interruptible_covers_cancel_after_task_done():
    async def go():
        async with FinesseMock(MockConfig(speed=200, sentence_latency_ms=1)) as mock:
            client = client_for(mock)
            async with client.realtime.connect() as rt:
                ctx = rt.context(voice_id=VOICE_ID)
                await ctx.send(TURN, finalize=True)
                await asyncio.sleep(0.5)
                wrapped = Interruptible(ctx)
                await wrapped.interrupt()
                after = [e async for e in wrapped]
            await client.close()
            return after

    after = run(go())
    assert not any(isinstance(e, AudioEvent) for e in after)
    assert isinstance(after[-1], TaskDone)


# ---- time to first audio --------------------------------------------------------------------

STALL = [("Sure, the flat on the third floor has", 0.0), (" two bedrooms.", 1.0), (" Bye.", 0.0)]


def test_ttfa_llm_stall_waits_for_idle_flush_by_default():
    async def go():
        async with FinesseMock() as mock:
            return await ttfa_turn(mock.base_url, "stall", STALL)

    r = run(go())
    assert r.ttfa_ms >= 800 and not r.within_budget


def test_ttfa_lower_idle_flush_recovers_budget():
    async def go():
        async with FinesseMock() as mock:
            return await ttfa_turn(mock.base_url, "stall", STALL, idle_flush_ms=200)

    r = run(go())
    assert 300 <= r.ttfa_ms < 800 and r.within_budget
