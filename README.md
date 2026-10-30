# JARVIS — Personal AI Desktop Assistant

A Claude.ai-style, multi-page AI assistant that runs **on your machine**. It chats, speaks out loud, controls your desktop (apps, volume, brightness, screenshots, shell commands), sets reminders, and gives you a spoken morning briefing — all behind an Approve/Decline safety card for risky actions.

Works on **Linux** (tested on Ubuntu 24.04 GNOME Wayland) and **Windows**.

---

## What it looks like

- **Browser UI** (`uvicorn api.main:app`) — React app served by FastAPI with SSE streaming, sidebar, voice, approvals, tasks, memory, settings.
- **Legacy Streamlit UI** (`streamlit run ui.py`) — still functional for parity and original UI.
- **Desktop overlay** (`python jarvis_desktop.py`) — system tray app with global hotkey (`Ctrl+Alt+J`). Press it, speak into the mic, JARVIS answers out loud without you closing your current app.

## Quick start (one page)

```bash
# 1. Clone / open the folder
cd /home/rokkun-23/Desktop/Agnet_Example

# 2. Create & activate virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. System libraries (Linux only)
sudo apt install -y libportaudio2   # microphone / system speech

# 5. Add your Groq API key to .env
cp .env.example .env
# edit .env and set GROQ_API_KEY=...

# 6. Run the browser version
uvicorn api.main:app --host 127.0.0.1 --port 8000

# 7. Open http://localhost:8000 in your browser
```

Then talk to JARVIS by typing or clicking the mic button.

---

## Two ways to use JARVIS

### A) React web app — `uvicorn api.main:app`

Best for chat, approvals, tasks, memory, settings, activity, usage, documents.

- Open `http://127.0.0.1:8000`
- Type normally, or enable hands-free voice mode once with the mic button. In voice mode, speech is sent automatically, replies are spoken aloud, and “yes” / “no” answer approval prompts. Microphone permission is required; Chrome or Edge is recommended.
- Toggle read replies aloud in chat/tools
- Use pages in sidebar: Chat, Today, Tasks, Memory, Documents, Activity, Usage, Settings

### B) Legacy Streamlit — `streamlit run ui.py`

Older full-featured UI kept functional in `app_pages`.

- Open `http://localhost:8501`
- Attach documents, configure location, habits, briefing

### C) Desktop overlay — `python jarvis_desktop.py`

Best for "don't interrupt my work" voice control.

Install the optional desktop dependencies in the same virtual environment as the API:

```powershell
# Windows
.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.venv\Scripts\python.exe jarvis_desktop.py
```

On Linux, install `libportaudio2` first; then run the equivalent `.venv/bin/python -m pip install -r requirements-desktop.txt` and start `jarvis_desktop.py`.

- The tray icon and voice overlay appear when JARVIS starts
- Press **`Ctrl+Alt+J`** (or click the tray icon) to bring the overlay back later
- Click and hold the mic, speak, and JARVIS answers out loud
- Overlay fades away — your app underneath stays untouched
- Works on both Linux and Windows

> **Note:** On Ubuntu/GNOME Wayland, `Ctrl+Alt+J` may not grab. Click the tray icon instead — everything else works the same.

---

## What JARVIS can do

| Say this | What happens |
|----------|--------------|
| *"What's on my screen?"* | Takes a screenshot, shows it, speaks confirmation |
| *"Open Chrome / VS Code / Calculator"* | Launches the app |
| *"Close Chrome"* | Asks for approval first (unsaved work), then closes |
| *"Volume to 40"* / *"Mute everything"* | Sets system volume, speaks confirmation |
| *"Brightness to 60"* | Sets screen brightness (laptops) |
| *"Run: ls -la"* | Runs shell command behind Approve/Decline card |
| *"Remind me to call Mom at 6pm"* | Saves a reminder; speaks *"Reminder: call Mom, due now"* at the time |
| *"How's my laptop?"* | System status: OS, uptime, RAM, disk, battery, volume, top processes |
| *"Give me my morning briefing"* | Overdue items, today's plan, one suggestion — spoken aloud |
| *"Nearest veg restaurant nearby"* / *"pharmacy near me open now"* | Nearby places from your saved home location (Google/Foursquare/OSM); OSM results sort by distance |

---

## Safety

Risky actions (`run_command`, `close_app`) always show an **Approve / Decline card** with the exact command before anything touches your computer. Declining means nothing runs.

---

## Step 1: How to log in and start automatically

When you log in to your laptop JARVIS will speak a time-aware greeting ("Good morning, sir. JARVIS online and standing by.") and prepare your morning briefing in the background. The system tray icon appears and stays.

To enable this:
1. System → Settings → Autostart (already configured via `~/.config/autostart/jarvis.desktop`)
2. Each JARVIS launch speaks the greeting and triggers the background watcher (reminders + briefing).

## What happens in the morning (the briefing card)

At your configured briefing time (default 08:00, change on Today → Briefing settings), the agent writes a short message with:
1) anything overdue, 2) what's due today, 3) a practical suggestion,
4) one recent decision, 5) any important unread email, 6) one tech headline.
The card appears at the top of every page and your desktop speaks "Morning briefing ready, sir."

## Email setup (optional — Gmail IMAP)

JARVIS can read your unread email subjects/senders during the briefing. Uses Gmail IMAP with an app password (read-only; credentials never leave your machine except to Gmail).

1. Turn on 2FA on your Google account.
2. Create an **App Password**: https://myaccount.google.com/apppasswords (16 characters).
3. Add to `.env`:
   ```
   GMAIL_ADDRESS=you@gmail.com
   GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
   ```
4. Restart the app. Next morning briefing will include an inbox digest.

If you skip this, JARVIS just says "Email not configured, skip" and continues briefing.

## "Hey JARVIS" wake word (experimental)

Run `wake_word.py` in a separate terminal: it listens to your mic constantly, and on detecting the wake word records your voice, transcribes via Whisper, asks the agent, and speaks the reply. See `wake_word.py` for wake-word model name.

## Habits (daily check-ins)

JARVIS tracks your daily habits with streaks.

- Chat: "log habit morning run", "list my habits", "what's my streak on B12?"
- Today page: an expander shows every habit with today's ✅/⬜ and 🔥 streak badge; tap "Log" to check in.
- Habits block appears in system prompt so the agent encourages streaks and gently nudges on missed days.
- Habits appear (mentioned briefly) in the morning briefing.

Streaks reset if you miss a day completely.

JARVIS brain runs on your desktop. Phone access: open browser to `http://<desktop-ip>:8501` while on the same Wi-Fi. See "Mobile access" in earlier README sections / README docs.

**Linux:**
```bash
# Already included: ~/.config/autostart/jarvis.desktop
# It launches jarvis_desktop.py when you log in
```

**Windows:**
Create a shortcut to `jarvis_desktop.py` in:
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```

---

## Cross-platform support

| Component | Linux | Windows |
|-----------|-------|---------|
| Chat UI (Streamlit) | ✅ | ✅ |
| React web app | ✅ | ✅ |
| Desktop overlay (PyQt6) | ✅ | ✅ |
| Volume control | `wpctl` | `pycaw` |
| Brightness | sysfs / `brightnessctl` | `screen-brightness-control` |
| Screenshots | CLI tools / XDG portal | `PIL.ImageGrab` |
| App launch | `xdg-open` / PATH | `os.startfile()` |
| Close app | `pgrep`/`pkill` | `psutil` |
| System stats | `/proc` + `psutil` | `psutil` |
| Popups | `notify-send` | `win10toast` |
| Speech | `spd-say` | `pyttsx3` |
| Shell commands | `/bin/bash` | `cmd.exe` |

---

## Project structure

```
Agnet_Example/
├── ui.py                 # Entry point — navigation + multi-page app
├── agent.py              # The JARVIS brain (LangGraph, tools, approvals, voice)
├── desktop.py            # Desktop control tools (cross-platform)
├── tts.py                # Voice replies (Groq Orpheus + Edge TTS fallback)
├── wake_word.py          # Always-listening "Hey Jarvis" (separate process)
├── jarvis_desktop.py     # System tray overlay app (Ctrl+Alt+J)
├── places.py             # Nearby places (Google / Foursquare / OSM)
├── app_reminders.py      # Background watcher — reminders + spoken briefing
├── app_briefing.py       # Morning briefing generation + settings
├── tasks.py              # Task database + tools
├── app_data.py           # Cached dashboard data + task counts
├── memory.py             # Memory, rules, decisions store
├── ui_theme.py           # Single stylesheet for all pages
├── jarvis/               # Packaged modules (agent, tasks, auth helpers)
├── api/                  # FastAPI backend
├── web/                  # React frontend
├── rag.py                # Document indexing + search
├── requirements.txt      # Python dependencies
├── .env                  # Your GROQ_API_KEY (create this)
├── .streamlit/config.toml# Theme configuration
├── app_pages/
│   ├── chat.py           # Main chat window
│   ├── today.py          # Today dashboard + briefing settings
│   ├── tasks.py          # Task management
│   ├── memory.py         # Long-term memory
│   ├── documents.py      # RAG document viewer
│   ├── activity.py       # Activity log + redacted timeline
│   ├── settings.py       # Models / voice / aliases / home location
│   └── usage.py          # Token / latency per call
├── screenshots/          # Captured screenshots (auto-pruned, not committed)
├── notes/                # Saved notes (not committed)
└── README.md             # This file
```

---

## Database (single file, scales cleanly)

All state lives in **`jarvis.db`** (SQLite, WAL mode, one file = one backup).

Override the location with `JARVIS_DB` (or `AGNET_TASKS_DB` for tests):
`JARVIS_DB=/tmp/scratch.db .venv/bin/python -c "from jarvis import agent; print(agent.ask_agent('hi', thread_id='t'))"`

For scaling / multi-user: `tasks`/`rules`/`decisions` tables already have a `user_id` column
(see `tasks CURRENT_USER` context var) — filter by user_id per request.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `GROQ_API_KEY missing` | Add `GROQ_API_KEY=sk-...` to `.env` |
| No sound / speech | Linux: `sudo apt install speech-dispatcher` and test `spd-say "hello"`. Windows: `pyttsx3` should work out of the box. |
| Mic not working | Check OS sound settings → input device. Test with another app first. |
| `Ctrl+Alt+J` does nothing | Wayland limitation — click the system tray icon instead. |
| Screenshot fails | Linux: `sudo apt install gnome-screenshot`. Windows: `Pillow` is already in requirements. |
| Port 8000 in use | Use `--port 8001` or stop process |
| Setup screen shows again | Wrong DB path or /tmp DB; check `JARVIS_DB` and resolved log |
| Tool calling not supported | Use allowlisted model from settings |
| 403/CSRF from dev server | Add dev origin to `JARVIS_ALLOWED_ORIGINS` |
| Overpass 502/busy | Retry / provider backoff |
| Groq daily limit | Resets per cap |
| Missing libportaudio2 | `sudo apt install libportaudio2` |
| Tailwind/PostCSS build error | `rm -rf node_modules && npm ci` |

---

## Roadmap (what's coming)

- **Wake word** (`wake_word.py`) — always-listening "Hey Jarvis" without pressing anything
- **Mobile access** — open browser to your laptop's IP on the same Wi-Fi
- **Auto-start** — already configured for Linux via `.config/autostart/`

---

## Web frontend (React)

Use Node.js **22.22.2 or newer** for the frontend build and test toolchain.

```bash
# terminal 1
uvicorn api.main:app --host 127.0.0.1 --port 8000

# terminal 2
cd web
npm ci
npm run dev
```

Dev server port defaults to 5173. Use an alternate port if desired:
```bash
cd web && npm run dev -- --port 15173
```

Dev server runs on port 5173 (`http://127.0.0.1:5173`). For CORS during development, set in `.env`:

```
JARVIS_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

If using port 15173 instead:
```
JARVIS_ALLOWED_ORIGINS=http://127.0.0.1:15173,http://localhost:15173
```

By default only same-origin (`http://127.0.0.1:8000`) is allowed. Production runs on port 8000 with no extra configuration.

## Testing

```bash
pytest -q
cd web && npm test
cd web && npx playwright test
```

Expected summaries:
- API tests: `13 passed`
- Frontend: `8 tests passed`
- Playwright validates configured smoke/layout tests

## Known limits

- Wake word dependency installation can fail on Python versions incompatible with some audio/ML packages.
- Not all desktop controls tested on every Linux flavor.
- `.env` and `jarvis.db` are never committed.

## License

Personal use. You own your data — everything lives in local SQLite databases on your machine.
