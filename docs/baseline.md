# Token / latency baseline

Captured 2026-10-28 on `groq:openai/gpt-oss-120b` pre-optimization baseline + after 2a/2b/2d/2e/3.

## Before optimization (measured once)

| # | Label | Prompt | Route | LLM calls | Prompt tok | Comp tok | Total | Latency ms |
|---|---|---|---|---|---|---|---|---|
| 1 | simple-hi | "Hi" | complex (120b) | 1 | 3,989 | 48 | 4,037 | 1,707 |
(unstable due to Groq daily token cap; full 12-turn matrix could not complete before quota)

## After 2a + 2b + 2d + 2e + 3 router (measured)

| label | Route | LLM calls | Prompt tok | Comp tok | Total | Latency ms |
|---|---|---|---|---|---|---|
| simple-hi | simple (20b) | 1 | 820 | 41 | 861 | 625 |
| simple-math | simple (20b) | 2 (adds 1 calculator tools round) | 828 | 48 | 876 | ~583 |
| simple-joke | simple | 1 | 825 | 40 | 865 | ~500 |
| desktop-status | fast | 0 | 0 | 0 | 0 | 0 |
| open-chrome | fast | 0 | 0 | 0 | 0 | 0 |
| set-volume-40 | fast | 0 | 0 | 0 | 0 | 0 |
| mute | fast | 0 | 0 | 0 | 0 | 0 |
| system-status | fast | 0 | 0 | 0 | 0 | 0 |
| take-screenshot | fast | 0 (tool runs via LLM if invoked by model) | – | – | – |
| task-add | (n/a during quota window — tool turn) | 2 | — 3,696 before | ~2,200 after | 27,463ms before → ~12,000 |
| task-list | (n/a during quota window) | 2 | — 3,684 | ~2,200 | ~25,000 ms |
| memory-recall | simple | 2 | ~2,349 | 111 | ~2,460 | 17,036 |
| rag | simple | 3 | ~3,302 | 858 | 4,160 | 25,575 |

Note on routing: after 2a/2b, "simple" model selection lands on 20b via the router
(only trivial prompt ~800 tok). Complex 120b tier picked only when triggered.
Daily guard switches complex->simple at >=80% TPD.

## Before/after key ratios
- "hi" prompt: 3,989 → 820 = **−79%**
- simple typical latency: 1,707 → 590 = −65%
- tools bound per turn: 36 → 5 (bare chat) / 14–24 (domain)
- tools reachable still 38 total (ToolNode).

## Tool output caps (already tight)
- read_note: 1500 chars
- web_search snippet: 200 chars
- check_email subject: 90 chars
- search_conversations result: 200 chars

## Verification
- Streaming path logs usage (non-null). Failed/rate-limited logged with status.
- Cron/Chat turn approve gate still works for run_command/close_app.
- AppTest sweep green (6 pages) at all steps produced.