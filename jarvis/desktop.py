"""
desktop.py - JARVIS-style desktop control (cross-platform: Linux + Windows).

Curated, mostly-instant tools (system status, open/close apps, volume,
brightness, screenshot, open anything) plus a general `run_command` that
ALWAYS passes through the Approve/Decline card first (see needs_approval
in agent.py). Everything runs as the logged-in user on THIS machine only.

Screenshot backends, tried in order:
  1. CLI tools if installed (grim / gnome-screenshot / scrot / spectacle / import)   [Linux]
  2. PIL ImageGrab                                                                     [Windows]
  3. the XDG Desktop Portal over D-Bus (works on Ubuntu GNOME Wayland; the desktop
     may ask the user to allow it once)                                                [Linux]
Screenshots land in screenshots/ (auto-pruned) and the chat renders them
as an image via the "SCREENSHOT:<path>" marker.
"""
from __future__ import annotations

import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

BASE_DIR = Path(__file__).resolve().parent.parent
SHOTS_DIR = BASE_DIR / "screenshots"
CMD_TIMEOUT = 60     # run_command gives up after this many seconds
OUTPUT_CAP = 4000    # chars of command output kept

IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")
IS_MAC = sys.platform == "darwin"


# --------------------------------------------------------------------------\n# small helpers\n# --------------------------------------------------------------------------

def _run(cmd, timeout: int = 15):
    """Run a command; None when the binary is missing or it timed out."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _clip(text: str) -> str:
    return text if len(text) <= OUTPUT_CAP else text[:OUTPUT_CAP] + f"\n... [truncated, {len(text)} chars]"


# --------------------------------------------------------------------------\n# volume\n# --------------------------------------------------------------------------

def _volume_get() -> str:
    if IS_WINDOWS:
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            level = volume.GetMasterVolumeLevelScalar()  # 0.0 to 1.0
            muted = volume.GetMute()
            return f"{round(level * 100)}%{' (muted)' if muted else ''}"
        except Exception:
            return "unknown"
    r = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    if r is not None and r.returncode == 0:
        m = re.search(r"([\d.]+)", r.stdout)
        if m:
            muted = "[MUTED]" in r.stdout
            return f"{round(float(m.group(1)) * 100)}%{' (muted)' if muted else ''}"
    return "unknown"


def _set_volume(percent: int) -> bool:
    if IS_WINDOWS:
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevelScalar(percent / 100.0, None)
            if percent > 0:
                volume.SetMute(0, None)
            return True
        except Exception:
            return False
    if shutil.which("wpctl"):
        r = _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{percent}%"])
        if r is not None and r.returncode == 0:
            if percent > 0:
                _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"])
            return True
    if shutil.which("pactl"):
        r = _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"])
        if r is not None and r.returncode == 0:
            return True
    return False


# --------------------------------------------------------------------------\n# brightness\n# --------------------------------------------------------------------------

def _backlight_dev():
    root = Path("/sys/class/backlight")
    if not root.exists():
        return None
    return next(iter(root.glob("*")), None)


def _brightness_get() -> str:
    if IS_WINDOWS:
        try:
            import screen_brightness_control as sbc
            return f"{sbc.get_brightness()[0]}%"
        except Exception:
            return ""
    dev = _backlight_dev()
    if dev is None:
        return ""
    try:
        cur = int((dev / "brightness").read_text())
        mx = max(1, int((dev / "max_brightness").read_text()))
        return f"{round(100 * cur / mx)}%"
    except OSError:
        return "unknown"


def _set_brightness(percent: int) -> bool:
    if IS_WINDOWS:
        try:
            import screen_brightness_control as sbc
            sbc.set_brightness(percent)
            return True
        except Exception:
            return False
    dev = _backlight_dev()
    if dev is None:
        return False
    try:
        mx = max(1, int((dev / "max_brightness").read_text()))
        (dev / "brightness").write_text(str(max(1, round(mx * percent / 100))))
        return True
    except (PermissionError, OSError):
        return False


# --------------------------------------------------------------------------\n# battery / uptime / processes\n# --------------------------------------------------------------------------

def _battery_get() -> str:
    try:
        import psutil
        bat = psutil.sensors_battery()
        if bat is None:
            return ""
        return f"{bat.percent}% ({'charging' if bat.power_plugged else 'discharging'})"
    except Exception:
        pass
    root = Path("/sys/class/power_supply")
    if not root.exists():
        return ""
    for bat in sorted(root.glob("BAT*")):
        try:
            cap = (bat / "capacity").read_text().strip()
            state = (bat / "status").read_text().strip()
            return f"{cap}% ({state})"
        except OSError:
            continue
    return ""


def _uptime() -> str:
    try:
        import psutil
        up = time.time() - psutil.boot_time()
        d, rem = divmod(int(up), 86400)
        h, m = divmod(rem, 3600)
        m //= 60
        return f"{d}d {h}h {m}m" if d else f"{h}h {m}m"
    except Exception:
        up_s = int(float(open("/proc/uptime").read().split()[0]))
        d, rem = divmod(up_s, 86400)
        h, m = divmod(rem, 3600)
        m //= 60
        return f"{d}d {h}h {m}m" if d else f"{h}h {m}m"


def _loadavg() -> str:
    try:
        import psutil
        return " ".join(f"{x:.2f}" for x in psutil.getloadavg())
    except Exception:
        return " ".join(open("/proc/loadavg").read().split()[:3])


def _top_processes(limit: int = 4):
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["name", "cpu_percent"]):
            try:
                procs.append((p.info["name"] or "", p.info["cpu_percent"] or 0))
            except Exception:
                continue
        procs.sort(key=lambda x: x[1], reverse=True)
        return procs[:limit]
    except Exception:
        pass
    r = _run(["ps", "-eo", "pcpu=,comm=", "--sort=-pcpu"])
    if r is not None and r.returncode == 0:
        out = []
        for ln in r.stdout.splitlines()[:limit]:
            parts = ln.split(None, 1)
            if len(parts) == 2:
                out.append((parts[1], parts[0]))
        return out
    return []


# --------------------------------------------------------------------------\n# desktop launcher lookup\n# --------------------------------------------------------------------------

def _find_desktop(name: str):
    """Match a program name against installed .desktop launchers (Linux only)."""
    low = name.lower()
    for root in ("/usr/share/applications", str(Path.home() / ".local/share/applications")):
        base = Path(root)
        if not base.exists():
            continue
        for f in sorted(base.glob("**/*.desktop")):
            try:
                txt = f.read_text(errors="ignore")
            except OSError:
                continue
            m = re.search(r"^Name=(.+)$", txt, re.M)
            if not m:
                continue
            dname = m.group(1).strip()
            if not (low == dname.lower() or low in f.stem.lower() or low in dname.lower()):
                continue
            em = re.search(r"^Exec=(.+)$", txt, re.M)
            if not em:
                continue
            toks = [t for t in shlex.split(em.group(1)) if not t.startswith("%")]
            if toks:
                return dname, toks
    return None


def _launch(argv: list[str], label: str) -> str:
    try:
        if IS_WINDOWS and len(argv) == 1:
            try:
                os.startfile(argv[0])
                return f"Launched {label}."
            except Exception:
                pass
        subprocess.Popen(argv,
                         start_new_session=IS_LINUX,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Launched {label}."
    except OSError as e:
        return f"Could not launch {label}: {e}"


# --------------------------------------------------------------------------\n# screenshot backends\n# --------------------------------------------------------------------------

def _shot_cli(dest: Path):
    """Try the simple CLI screenshot tools; returns the backend name on success."""
    backends = [
        (["grim", str(dest)], "grim"),
        (["gnome-screenshot", "-f", str(dest)], "gnome-screenshot"),
        (["scrot", str(dest)], "scrot"),
        (["spectacle", "-b", "-n", "-o", str(dest)], "spectacle"),
        (["import", "-window", "root", str(dest)], "imagemagick"),
    ]
    for cmd, name in backends:
        if not shutil.which(cmd[0]):
            continue
        r = _run(cmd, timeout=20)
        if r is not None and r.returncode == 0 and dest.exists():
            return name
    return None


def _shot_windows(dest: Path) -> bool:
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(dest)
        return True
    except Exception:
        return False


def _shot_portal(dest: Path):
    """XDG Desktop Portal over D-Bus - the sanctioned way on GNOME Wayland.
    Returns (ok, detail). The desktop may show an allow/cancel prompt."""
    if IS_WINDOWS:
        return False, "portal not available on Windows"

    try:
        import asyncio

        from dbus_next import Variant
        from dbus_next.aio import MessageBus
        from dbus_next.constants import BusType
    except ImportError:
        return False, "dbus-next is not installed (.venv/bin/pip install dbus-next)"

    async def _grab(interactive: bool, wait: float):
        """-> (state, uri) with state: ok | denied | cancelled | timeout | error"""
        from dbus_next.introspection import Node
        from dbus_next.message import Message

        async def _raw_node(path: str) -> Node:
            reply = await bus.call(Message(
                destination="org.freedesktop.portal.Desktop", path=path,
                interface="org.freedesktop.DBus.Introspectable",
                member="Introspect"))
            if reply is None:
                raise RuntimeError("no introspect reply")
            return Node.parse(_sanitize_xml(reply.body[0]))

        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        try:
            node = await _raw_node("/org/freedesktop/portal/desktop")
            node.interfaces = [i for i in node.interfaces
                               if i.name == "org.freedesktop.portal.Screenshot"]
            obj = bus.get_proxy_object("org.freedesktop.portal.Desktop",
                                       "/org/freedesktop/portal/desktop", node)
            scr = obj.get_interface("org.freedesktop.portal.Screenshot")
            handle = await scr.call_screenshot("", {"interactive": Variant("b", interactive)})
            node2 = await _raw_node(handle)
            node2.interfaces = [i for i in node2.interfaces
                                if i.name == "org.freedesktop.portal.Request"]
            req = bus.get_proxy_object("org.freedesktop.portal.Desktop", handle, node2)\
                      .get_interface("org.freedesktop.portal.Request")
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()

            def _cb(code, results):
                if not fut.done():
                    fut.set_result((code, results))

            req.on_response(_cb)
            try:
                code, results = await asyncio.wait_for(fut, wait)
            except asyncio.TimeoutError:
                return ("timeout", "")
            if code == 0:
                uri = results.get("uri")
                return ("ok", str(uri.value if hasattr(uri, "value") else uri))
            if code == 1:
                return ("cancelled", "")
            if code == 2:
                return ("denied", "")
            return (f"code{code}", "")
        finally:
            try:
                bus.disconnect()
            except Exception:
                pass

    def _save(uri: str) -> bool:
        path = Path(uri.replace("file://", ""))
        if path.exists():
            shutil.copyfile(path, dest)
            return True
        return False

    try:
        state, uri = asyncio.run(_grab(False, 8))
        if state == "ok" and _save(uri):
            return True, "silently via the XDG portal (permission granted)"
        if state == "cancelled":
            return False, "the desktop declined the silent screenshot"
        state, uri = asyncio.run(_grab(True, 45))
        if state == "ok" and _save(uri):
            return True, "via the screenshot panel"
        if state == "cancelled":
            return False, "cancelled in the screenshot panel"
        if state == "timeout":
            return False, ("the screenshot panel opened but no capture happened "
                           "within 45 seconds - if an older panel is still on "
                           "screen, finish or cancel it first")
        return False, f"interactive capture failed ({state})"
    except Exception as e:
        return False, f"XDG portal: {e}"


def _prune_shots(keep: int = 8) -> None:
    for f in sorted(SHOTS_DIR.glob("shot-*.png"))[:-keep]:
        try:
            f.unlink()
        except OSError:
            pass


def _sanitize_xml(xml: str) -> str:
    """Drop members with hyphens in their names (the portal's
    'power-saver-enabled' property) - dbus-next refuses to parse them."""
    xml = re.sub(r'<(property|method|signal)\b[^>]*name="[^"]*-[^"]*"[^>]*/>', "", xml)
    return re.sub(r'<(property|method|signal)\b[^>]*name="[^"]*-[^"]*"[^>]*>.*?</\1>',
                  "", xml, flags=re.S)


def _recent_desktop_shot(after: float):
    """Newest screenshot created after 'after' in the desktop's save locations."""
    best = None
    for d in (Path.home() / "Pictures", Path.home() / "Pictures" / "Screenshots"):
        if not d.is_dir():
            continue
        for f in list(d.glob("*.png")) + list(d.glob("*.jpg")):
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            if m >= after and (best is None or m > best[0]):
                best = (m, f)
    return best[1] if best else None


# --------------------------------------------------------------------------\n# the tools\n# --------------------------------------------------------------------------

@tool
def system_status() -> str:
    """Snapshot of the user's machine: OS, uptime, CPU load, RAM, disk space,
    battery, volume, brightness and the top processes. Read-only - use for
    'how is my laptop', 'battery?', 'how much disk is left', 'what's using
    the CPU'. Works on Linux and Windows."""
    lines = []
    try:
        plat = platform.platform()
        lines.append(f"{plat} - up {_uptime()}, load {_loadavg()}")
    except OSError:
        lines.append("OS info unavailable")

    try:
        import psutil
        mem = psutil.virtual_memory()
        du = psutil.disk_usage("/")
        bat = _battery_get()
        lines.append(
            f"RAM {mem.used / 1e6:.1f}/{mem.total / 1e6:.1f} GB ({mem.percent}%), "
            f"disk / {du.used / 2**30:.0f}/{du.total / 2**30:.0f} GB "
            f"({round(100 * du.used / du.total)}%), battery {bat or 'none (plugged)'}"
        )
    except Exception:
        lines.append("RAM / disk unavailable")

    bits = [f"volume {_volume_get()}"]
    br = _brightness_get()
    if br:
        bits.append(f"brightness {br}")
    lines.append(", ".join(bits))

    top = _top_processes()
    if top:
        lines.append("top: " + ", ".join(f"{p} {float(c):.0f}%" for p, c in top))
    return "\n".join(lines)


# common app-name synonyms -> the real binary or a web URL
_APP_ALIASES = {
    "chrome": "google-chrome",
    "google chrome": "google-chrome",
    "edge": "microsoft-edge",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "wa": "https://web.whatsapp.com",
    "telegram": "https://web.telegram.org",
    "yt": "https://youtube.com",
    "youtube": "https://youtube.com",
    "gmail": "https://mail.google.com",
    "google": "https://google.com",
    "reddit": "https://reddit.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "facebook": "https://facebook.com",
    "fb": "https://facebook.com",
    "docs": "https://docs.google.com",
    "gdrive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "calendar": "https://calendar.google.com",
    "maps": "https://maps.google.com",
    "notion": "https://notion.so",
    "spotify": "https://open.spotify.com",
}


@tool
def open_app(app: str) -> str:
    """Open something on the user's desktop: launch a program by name
    ('calculator', 'firefox', 'code'), or open a file, folder or URL by
    passing a path or link ('~/Documents', '/home/u/report.pdf',
    'https://example.com'). Instant, no approval needed."""
    target = app.strip()
    # common-name / web-app alias resolution (e.g. "chrome" -> "google-chrome",
    # "whatsapp" -> https://web.whatsapp.com)
    _alias = _APP_ALIASES.get(target.lower().strip())
    if _alias:
        target = _alias
    urlish = bool(re.match(r"^[a-z][a-z0-9+.-]*://", target, re.I))
    pathish = target.startswith(("/", "~", "./")) or target.startswith("$HOME")
    if IS_WINDOWS:
        pathish = pathish or target.startswith("\\") or re.match(r"^[a-zA-Z]:", target)

    if urlish or pathish:
        if not urlish:
            p = Path(os.path.expandvars(os.path.expanduser(target)))
            if not p.exists():
                return f"No such file or folder: {target}"
        if IS_WINDOWS:
            try:
                os.startfile(target)
                return f"Opened {target}."
            except Exception as e:
                return f"Could not open {target}: {e}"
        r = _run(["xdg-open", target], timeout=20)
        if r is not None and r.returncode == 0:
            return f"Opened {target}."
        err = (r.stderr if r is not None else "xdg-open not installed").strip()[:200]
        return f"xdg-open failed: {err}"

    exe = shutil.which(target)
    if exe:
        return _launch([exe], f"{target} ({exe})")
    if not IS_WINDOWS:
        found = _find_desktop(target)
        if found:
            dname, argv = found
            return _launch(argv, f"{dname}")
    candidates = []
    low_t = target.lower()
    for root in ("/usr/share/applications", str(Path.home() / ".local/share/applications")):
        base = Path(root)
        if not base.exists():
            continue
        for f in base.glob("**/*.desktop"):
            try:
                nm = next((ln.split("=",1)[1] for ln in f.read_text(errors="ignore").splitlines()
                           if ln.startswith("Name=")), "")
            except OSError:
                continue
            if low_t in f.stem.lower() or low_t in (nm or "").lower():
                candidates.append(nm or f.stem)
    if candidates:
        return ("'" + target + "' was not found, but close matches exist: "
                + ", ".join(list(dict.fromkeys(candidates))[:5]) + ". Try one of those names.")
    return ("'" + target + "' was not found on PATH and has no launcher. "
            "Try the web equivalent (e.g. 'whatsapp' opens web.whatsapp.com), "
            "or run_command if it needs installing.")

@tool
def close_app(app: str) -> str:
    """Close a running program by name ('firefox', 'code'). The user must
    approve this first - closing can lose unsaved work."""
    name = app.strip()
    low = name.lower()
    mine = {os.getpid(), os.getppid()}
    pids: list[int] = []

    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pname = proc.info.get("name") or ""
                if pname.lower() == low or low in pname.lower():
                    if proc.pid not in mine:
                        pids.append(proc.pid)
            except Exception:
                continue
    except Exception:
        pass

    if not pids and IS_LINUX:
        for args in (["pgrep", "-x", name], ["pgrep", "-f", name]):
            r = _run(args)
            if r is not None and r.returncode == 0:
                pids = [int(p) for p in r.stdout.split()
                        if p.isdigit() and int(p) not in mine]
                if pids:
                    break

    if not pids:
        return f"No running process named '{name}' (or only our own)."

    closed = 0
    for pid in pids:
        try:
            if IS_WINDOWS:
                import psutil
                psutil.Process(pid).terminate()
            else:
                os.kill(pid, 15)  # SIGTERM: polite close
            closed += 1
        except (OSError, Exception):
            pass
    time.sleep(0.8)
    return (f"Sent a close to {closed} '{name}' process(es): "
            f"{', '.join(map(str, pids))}.")


@tool
def set_volume(percent: int) -> str:
    """Set the system output volume, 0 (silent) to 100. Instant, no approval.
    Anything above 0 also unmutes. Use 0 to silence everything."""
    pct = max(0, min(100, int(percent)))
    if _set_volume(pct):
        return f"Volume set to {_volume_get()}."
    return "Could not set volume on this machine (install pycaw on Windows, or wpctl/pactl on Linux)."


@tool
def set_brightness(percent: int) -> str:
    """Set the screen backlight brightness, 1-100. Instant, no approval.
    Works on laptops with a backlight; returns a clear message otherwise."""
    pct = max(1, min(100, int(percent)))
    if IS_WINDOWS:
        if _set_brightness(pct):
            return f"Brightness set to {pct}%."
        return ("Could not set brightness on Windows - "
                "install screen-brightness-control (.venv/bin/pip install screen-brightness-control).")
    dev = _backlight_dev()
    if dev is None:
        return ("This machine reports no screen backlight (desktop/VM) - "
                "brightness is not adjustable here.")
    if _set_brightness(pct):
        return f"Brightness set to {pct}%."
    return ("No permission to change brightness - install brightnessctl "
            "(sudo apt install brightnessctl).")


@tool
def take_screenshot() -> str:
    """Capture the user's screen and show it in the chat - use when they ask
    'what's on my screen', 'show me the window', or want to see an error.
    Read-only. Returns a SCREENSHOT:<path> marker that the chat renders as
    an image."""
    SHOTS_DIR.mkdir(exist_ok=True)
    _prune_shots()
    dest = SHOTS_DIR / f"shot-{datetime.now():%Y%m%d-%H%M%S}.png"
    started = time.time()

    how = _shot_cli(dest)
    if how and dest.exists():
        return f"SCREENSHOT:{dest}\nCaptured with {how}."

    if IS_WINDOWS:
        if _shot_windows(dest):
            return f"SCREENSHOT:{dest}\nCaptured with PIL ImageGrab."

    ok, why = _shot_portal(dest)
    if not ok:
        # the portal helper sometimes saves the file but loses the uri, and the
        # user may press PrintScreen while the panel is up - poll for a new file
        for _ in range(12):
            found = _recent_desktop_shot(started - 2)
            if found:
                try:
                    shutil.copyfile(found, dest)
                    ok, why = True, ""
                    break
                except OSError:
                    pass
            time.sleep(0.5)

    if ok and dest.exists():
        return f"SCREENSHOT:{dest}\nCaptured {why or 'from the desktop'}."
    return ("Could not take a screenshot automatically: no CLI tool is installed "
            "and the desktop portal did not deliver a file (" + (why or "no backend")
            + "). Tip: press PrintScreen yourself and ask me again right away - "
            "I'll pick the new file up from ~/Pictures. A permanent fix: "
            "sudo apt install gnome-screenshot")


@tool
def run_command(command: str) -> str:
    """Run a shell command on the user's own desktop - JARVIS-style control of
    anything the other tools do not cover (files, apps, settings, scripts,
    system queries). The user ALWAYS approves the exact command first, so
    keep it short and safe. NEVER use destructive commands (rm -rf, shutdown,
    reboot, overwriting files, changing system config) unless the user
    explicitly asked for that exact action. Prefer the dedicated tools
    (open_app, set_volume, system_status, ...) whenever one fits."""
    try:
        p = subprocess.run(command, shell=True,
                           executable=("/bin/bash" if IS_LINUX else None),
                           capture_output=True, text=True, timeout=CMD_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"Command timed out after {CMD_TIMEOUT}s: {command}"
    out = ((p.stdout or "") + (p.stderr or "")).strip() or "(no output)"
    return f"exit {p.returncode}\n{_clip(out)}"


DESKTOP_TOOLS = [system_status, open_app, close_app, set_volume,
                 set_brightness, take_screenshot, run_command]


def validate_alias_text(text: str):
    """Validate the editor text: each spec must be a bare executable on PATH or
    an https:// URL. Returns (ok, errors, parsed_dict)."""
    import os, re
    parsed = {}
    errors = []
    for n, line in enumerate((text or "").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "->" in line:
            key, _, spec = line.partition("->")
        elif "=" in line:
            key, _, spec = line.partition("=")
        else:
            errors.append(f"line {n}: no '->' or '=' in {line!r}")
            continue
        key, spec = key.strip().lower(), spec.strip()
        if not key or not spec:
            errors.append(f"line {n}: empty alias or spec")
            continue
        if re.search(r"[\s;|&$`<>]", key) or chr(34) in key or chr(39) in key:
            errors.append(f"line {n}: alias {key!r} contains spaces/metachars")
            continue
        if not re.fullmatch(r"[a-z0-9 _\-]+", key):
            errors.append(f"line {n}: alias {key!r} has invalid chars")
            continue
        if spec.lower().startswith("https://"):
            if any(c in spec for c in (";", "|", "&", "$", "`", "\"", "'", "<", ">")):
                errors.append(f"line {n}: spec contains shell metachars")
                continue
            parsed[key] = spec
            continue
        if re.search(r"[\s;|&$`<>]", spec) or chr(34) in spec or chr(39) in spec:
            errors.append(f"line {n}: spec {spec!r} must be a bare executable or https:// URL")
            continue
        if os.path.sep in spec:
            errors.append(f"line {n}: spec {spec!r} must not contain path separators")
            continue
        if shutil.which(spec) is None:
            errors.append(f"line {n}: {spec!r} is not on PATH (not executable)")
            continue
        if spec.lower() in ("rm", "rmdir", "dd", "shred", "mkfs", "chmod", "chown", "bash", "sh", "zsh", "ksh", "csh", "tcsh", "fish", "python", "python3"):
            errors.append(f"line {n}: {spec!r} is too dangerous to fast-launch")
            continue
        parsed[key] = spec
    return (len(errors) == 0), errors, parsed


def get_aliases() -> dict:
    """Fast-path alias table, merging code defaults with user settings.

    Base `_APP_ALIASES` is immutable code (never writable by agents).
    User overrides live in settings under key 'fast_path_aliases':
      alias -> spec   (one per line, e.g.  "wa  ->  https://web.whatsapp.com")
      alias = spec
    No agent tool reads/writes this key; only the Settings UI page (and this
    helper) touches it.
    """
    out = dict(_APP_ALIASES)
    try:
        from jarvis.app_briefing import get_setting
        raw = (get_setting("fast_path_aliases", "") or "").strip()
        if raw:
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "->" in line:
                    k, _, v = line.partition("->")
                elif "=" in line:
                    k, _, v = line.partition("=")
                else:
                    continue
                k, v = k.strip().lower(), v.strip()
                if k and v:
                    out[k] = v
    except Exception:
        pass
    return out
