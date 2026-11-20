"""Run the turn-taking benchmark offline against the local mock and print a report.

    python bench.py            # prints tables, writes results/results.json
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import platform

import flam_finesse

from finesse_mock import FinesseMock, MockConfig
from harness import as_dict, barge_in_turn, ttfa_turn

# Three sentences, 91 characters: about 5.9 s of speech in the mock's length model
# (65 ms per character, rounded to 100 ms chunks per sentence).
TURN = "The flat has two bedrooms and a balcony. It gets morning light. Want to visit this weekend?"

# The LLM pauses 1.0 s inside its first sentence (tool call, retrieval, slow token).
STALL = [("Sure, the flat on the third floor has", 0.0), (" two bedrooms.", 1.0),
         (" Want to visit?", 0.05)]
# Same pause, but the LLM's first chunk is already a full sentence.
PUNCTUATED = [("Sure, I can help.", 0.0), (" The flat has two bedrooms.", 1.0),
              (" Want to visit?", 0.05)]


async def run() -> dict:
    barge = []
    for speed in (1.0, 2.0, 4.0, 8.0):
        async with FinesseMock(MockConfig(speed=speed)) as mock:
            for use_fix in (False, True):
                r = await barge_in_turn(mock.base_url, TURN, barge_in_after_s=1.0,
                                        use_fix=use_fix, speed=speed)
                barge.append(as_dict(r))

    ttfa = []
    async with FinesseMock(MockConfig()) as mock:
        ttfa.append(as_dict(await ttfa_turn(mock.base_url, "llm_stall_unpunctuated", STALL)))
        ttfa.append(as_dict(await ttfa_turn(mock.base_url, "llm_stall_unpunctuated", STALL,
                                            idle_flush_ms=200)))
        ttfa.append(as_dict(await ttfa_turn(mock.base_url, "llm_stall_after_full_sentence",
                                            PUNCTUATED)))
    return {
        "env": {"python": platform.python_version(), "flam_finesse": flam_finesse.__version__,
                "server": "local mock (finesse_mock.py), NOT Flam's service"},
        "barge_in": barge,
        "ttfa": ttfa,
    }


def report(res: dict) -> str:
    lines = ["## Barge-in: cancel() after 1.0 s of a ~5.9 s turn", "",
             "| generation speed | player | task_done already in? | stale speech after cancel | silence latency | turn end |",
             "|---|---|---|---|---|---|"]
    for r in res["barge_in"]:
        lines.append(f"| {r['speed']:.0f}x realtime | {r['mode']} | {r['server_done_before_cancel']} "
                     f"| {r['stale_audio_s']:.2f} s "
                     f"| {r['silence_latency_ms']:.0f} ms | {r['turn_end_ms']:.0f} ms |")
    lines += ["", "## Time to first audio (mock: 150 ms per sentence, budget 800 ms)", "",
              "| scenario | idle_flush_ms sent | TTFA | within 800 ms |", "|---|---|---|---|"]
    for r in res["ttfa"]:
        flush = r["idle_flush_ms"] if r["idle_flush_ms"] is not None else "none (mock default 800)"
        lines.append(f"| {r['scenario']} | {flush} | {r['ttfa_ms']:.0f} ms | {r['within_budget']} |")
    return "\n".join(lines)


def main() -> None:
    res = asyncio.run(run())
    out = pathlib.Path(__file__).parent / "results"
    out.mkdir(exist_ok=True)
    (out / "results.json").write_text(json.dumps(res, indent=2))
    text = report(res)
    (out / "report.md").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
