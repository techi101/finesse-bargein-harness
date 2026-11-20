## Barge-in: cancel() after 1.0 s of a ~5.9 s turn

| generation speed | player | task_done already in? | stale speech after cancel | silence latency | turn end |
|---|---|---|---|---|---|
| 1x realtime | sdk_pattern | False | 0.00 s | 0 ms | 1 ms |
| 1x realtime | interruptible | False | 0.00 s | 0 ms | 1 ms |
| 2x realtime | sdk_pattern | False | 1.00 s | 1086 ms | 1086 ms |
| 2x realtime | interruptible | False | 0.00 s | 0 ms | 2 ms |
| 4x realtime | sdk_pattern | False | 1.70 s | 1841 ms | 1841 ms |
| 4x realtime | interruptible | False | 0.00 s | 0 ms | 2 ms |
| 8x realtime | sdk_pattern | True | 4.80 s | 5288 ms | 5288 ms |
| 8x realtime | interruptible | True | 0.00 s | 0 ms | 0 ms |

## Time to first audio (mock: 150 ms per sentence, budget 800 ms)

| scenario | idle_flush_ms sent | TTFA | within 800 ms |
|---|---|---|---|
| llm_stall_unpunctuated | none (mock default 800) | 956 ms | False |
| llm_stall_unpunctuated | 200 | 367 ms | True |
| llm_stall_after_full_sentence | none (mock default 800) | 150 ms | True |
