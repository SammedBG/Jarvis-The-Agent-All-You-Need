import os
import sys

# make sure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
os.environ.setdefault("JARVIS_DB", "/tmp/opencode/tf.db")

from jarvis.agent import _fast_command


FAST = {
    "mute", "system status", "open chrome", "Set volume to 40",
    "take screenshot", "unmute",
}
NOT_FAST = {
    "open ~/.ssh", "open ../../etc/passwd", "open file.sh", "open C:\\",
    "open a.exe", "open chrome; ls", "open chrome and delete my notes",
    "volume 400",
}


def test_whitelisted_runs():
    assert _fast_command("mute") is not None
    assert _fast_command("system status") is not None
    r = _fast_command("volume 400")
    assert r is not None and "range" in r["reply"]


def test_sensitive_and_multi_intent_fall_through():
    for q in NOT_FAST - {"volume 400"}:
        assert _fast_command(q) is None, q


def test_run_command_and_close_app_never_fast():
    assert _fast_command("run command ls -la") is None
    assert _fast_command("close chrome") is None


if __name__ == "__main__":
    test_whitelisted_runs()
    test_sensitive_and_multi_intent_fall_through()
    test_run_command_and_close_app_never_fast()
    print("test_fast_path OK")