"""Safety gate tests for backend startup."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
PYTHON = sys.executable
REAL_DB = str(Path(ROOT) / "jarvis.db")
TEST_DB = str(Path(tempfile.gettempdir()) / "jarvis-safety-test.db")

# never touch the real DB
os.environ.setdefault("JARVIS_DB", TEST_DB)
os.environ.setdefault("AGNET_TASKS_DB", TEST_DB)


def test_bind_host_loopback_ok():
    from api.main import validate_bind_host
    assert validate_bind_host("127.0.0.1") is True
    assert validate_bind_host("localhost") is True
    assert validate_bind_host("::1") is True


def test_zero_string_does_not_enable_safety_bypasses(monkeypatch):
    from api.main import _env_enabled, validate_bind_host

    monkeypatch.setenv("JARVIS_FAKE_AGENT", "0")
    monkeypatch.setenv("JARVIS_TEST_MODE", "false")
    monkeypatch.setenv("JARVIS_ALLOW_REMOTE", "0")
    monkeypatch.setenv("JARVIS_ALLOW_REMOTE_FLAG", "false")
    assert not _env_enabled("JARVIS_FAKE_AGENT")
    assert not _env_enabled("JARVIS_TEST_MODE")
    assert validate_bind_host("0.0.0.0") is False


def test_bind_host_remote_refused():
    env = os.environ.copy()
    env["JARVIS_DB"] = TEST_DB
    env["AGNET_TASKS_DB"] = TEST_DB
    env.pop("JARVIS_ALLOW_REMOTE", None)
    env.pop("JARVIS_FAKE_AGENT", None)
    proc = subprocess.run(
        [PYTHON, "api/main.py", "--host", "0.0.0.0"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    print("stdout:", proc.stdout[:200])
    print("stderr:", proc.stderr[:400])
    assert proc.returncode != 0
    assert "refusing to bind" in proc.stderr or "refusing" in (proc.stdout + proc.stderr).lower()


def test_dummy_key_refused():
    env = os.environ.copy()
    env["JARVIS_DB"] = TEST_DB
    env["AGNET_TASKS_DB"] = TEST_DB
    env["GROQ_API_KEY"] = "dummy"
    env.pop("JARVIS_FAKE_AGENT", None)
    env.pop("JARVIS_TEST_MODE", None)
    proc = subprocess.run(
        [PYTHON, "api/main.py", "--host", "127.0.0.1"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    print("stderr:", proc.stderr[:300])
    assert proc.returncode != 0
    combined = proc.stdout + proc.stderr
    assert "GROQ_API_KEY is missing" in combined or "invalid" in combined.lower()


def test_validate_startup_with_fake_agent_ok():
    os.environ["JARVIS_FAKE_AGENT"] = "1"
    try:
        os.environ["GROQ_API_KEY"] = "dummy"
        from api.main import validate_startup
        validate_startup()  # should not raise
        print("validate_startup with fake agent OK")
    finally:
        os.environ.pop("JARVIS_FAKE_AGENT", None)
