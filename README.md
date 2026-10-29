# JARVIS — Personal AI Desktop Assistant

A Claude.ai-style, multi-page AI assistant that runs **on your machine**. It chats, speaks out loud, controls your desktop (apps, volume, brightness, screenshots, shell commands), sets reminders, and gives you a spoken morning briefing — all behind an Approve/Decline safety card for risky actions.

Works on **Linux** (tested on Ubuntu 24.04 GNOME Wayland) and **Windows**.

---

## What it looks like

- **Browser UI** (`streamlit run ui.py`) — Claude.ai-style chat with warm dark palette, sidebar, typing indicator, voice input, file attach, screenshot display, tool timeline, and approval cards.
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
echo "GROQ_API_KEY=sk-your-key-here" > .env

# 6. Run the browser version
streamlit run ui.py

# 7. Open http://localhost:8501 in your browser
```

Then talk to JARVIS by typing or clicking the mic button.

---

## Two ways to use JARVIS

### A) Browser version — `streamlit run ui.py`

Best for documents, tasks, rules, briefing settings, and phone access. Use **Settings → Home location** to geocode your area; JARVIS rounds coordinates to 2 decimals and never logs the full value.

- Open `http://localhost:8501`
- Type or click the 🎤 mic to speak
- Toggle **"Read replies aloud"** in the chat sidebar to hear answers
- Attach `.txt` / `.md` / `.pdf` files — they get indexed and you can ask about them
- Use the Today page for tasks, rules, decisions, and morning briefing settings

### B) Desktop overlay — `python jarvis_desktop.py`

Best for "don't interrupt my work" voice control.

- A tray icon appears; press **`Ctrl+Alt+J`** (or click the icon)
- An overlay pops up on top of your current window
- Click the mic, speak, JARVIS answers out loud
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
| Port 8501 in use | `streamlit run ui.py --server.port 8502` |

---

## Roadmap (what's coming)

- **Wake word** (`wake_word.py`) — always-listening "Hey Jarvis" without pressing anything
- **Mobile access** — open browser to your laptop's IP on the same Wi-Fi
- **Auto-start** — already configured for Linux via `.config/autostart/`

---

## Web frontend (React)

```bash
# in a separate terminal: start the API backend
cd /home/rokkun-23/Desktop/Agnet_Example
uvicorn api.main:app --host 127.0.0.1 --port 8000

# start the React dev server (proxies /api -> 127.0.0.1:8000)
cd web
npm install
npm run dev
```

The built frontend is served by FastAPI at `/` (after `npm run build`). The dev server proxies API requests with credentials so the HttpOnly session cookie survives.

Dev server runs on port 5173 (`http://127.0.0.1:5173`). For CORS during development, set in `.env`:

```
JARVIS_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

By default only same-origin (`http://127.0.0.1:8000`) is allowed. Production runs on port 8000 with no extra configuration.

## License

Personal use. You own your data — everything lives in local SQLite databases on your machine.