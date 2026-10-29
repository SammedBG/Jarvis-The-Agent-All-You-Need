import os, time, sqlite3, re, shutil, datetime
BASE = "/home/rokkun-23/Desktop/Agnet_Example"
sys = None
import sys as _s
_s.path.insert(0, BASE)
os.environ["JARVIS_DB"] = os.environ.get("JARVIS_DB", "/tmp/opencode/baseline.db")
shutil.copyfile("jarvis.db", "/tmp/opencode/baseline.db")
c = sqlite3.connect("/tmp/opencode/baseline.db")
# ensure checkpoint
c.execute("PRAGMA wal_checkpoint(TRUNCATE)"); c.commit(); c.close()

from jarvis import agent  # jarvis.agent as agent

challenge_id = f"base-{datetime.datetime.now().strftime('%H%M%S')}"
TURNS = [
    ("simple-hi",        "Hi"),
    ("simple-math",      "What's 15% of 840?"),
    ("simple-joke",      "Tell me a short joke."),
    ("desktop-vol",      "Set volume to 40"),
    ("desktop-open",     "open chrome"),
    ("desktop-status",   "System status"),
    ("task-add",         "Add task call mom tomorrow at 6pm"),
    ("task-list",        "List my tasks"),
    ("task-complete",    "COMPLETE_PLACEHOLDER"),  # resolved after add
    ("memory-remember",  "Remember that I like black coffee"),
    ("memory-recall",    "What do you know about me?"),
    ("rag-question",     "Summarize the business report for me."),
]

# resolve task id after add_turn done offline
def usage_rows_for_thread(tid):
    c = sqlite3.connect("/tmp/opencode/baseline.db")
    c.row_factory = sqlite3.Row
    r = c.execute("SELECT prompt_tokens pp, completion_tokens cp, latency_ms lm FROM usage WHERE thread_id=? ", (tid,)).fetchall()
    return [{"p": x["pp"], "c": x["cp"], "l": x["lm"]} for x in r]

# thread per turn? keep separate thread ids per turn so each turn isolated
# but conversation muscle = separate threads. Realistic mixed thread also fine.
# We'll use per-turn thread ids each named base-N to isolate cleanly.
results = []
turn_no = 0
for label, prompt in TURNS:
    tid = f"{challenge_id}-{turn_no}"
    if prompt == "COMPLETE_PLACEHOLDER":
        # find task id from prior add turn
        import sqlite3 as _s
        cc = _s.connect("/tmp/opencode/baseline.db")
        row = cc.execute("SELECT id FROM tasks ORDER BY id DESC LIMIT 1").fetchone()
        prompt = f"Complete task #{row[0]}"
    turn_no += 1
    # for chat flow use streaming
    before = len(sqlite3.connect("/tmp/opencode/baseline.db").execute("SELECT 1 FROM usage").fetchall())
    t0 = time.time()
    try:
        evs = list(agent.ask_agent_stream(prompt, tid))
        err = None
        reply = next((e.get("text") for e in reversed(evs) if e.get("type") == "answer"), "")
        elapsed = time.time() - t0
    except Exception as e:
        err = str(e); reply = ""; elapsed = time.time() - t0
    # capture usage rows added this turn by thread id
    rows = usage_rows_for_thread(tid)
    tot_p = sum(r["p"] for r in rows); tot_c = sum(r["c"] for r in rows)
    tot_l = sum(r["l"] for r in rows)
    n_calls = len(rows)
    print(f"\n[{label}] prompt='{prompt[:60]}' err={err}")
    print(f"   LLM calls: {n_calls}, prompt={tot_p}, comp={tot_c}, total={tot_p+tot_c}, latency={tot_l}ms (wall {elapsed:.1f}s)")
    print(f"   reply: {reply[:150].replace(chr(10),' ')}")
    results.append((label, prompt, err, n_calls, tot_p, tot_c, tot_l, elapsed, reply[:240]))
    time.sleep(4)

# dump to json for baseline.md
import json
json.dump(results, open("/tmp/opencode/baseline_results.json","w"), indent=2, default=str)
print("\nBASELINE_DONE")
PY