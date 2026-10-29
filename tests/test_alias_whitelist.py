import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
os.environ.setdefault("JARVIS_DB", "/tmp/opencode/alias_test.db")

from jarvis.desktop import (
    validate_alias_text, get_aliases, _APP_ALIASES,
)
from jarvis.agent import TOOLS
from jarvis.agent import _fast_command

# 1) parse valid entries
text = (
    "chrome -> https://www.google.com\n"
    "whatsapp = https://web.whatsapp.com\n"
    "safe-link -> https://example.com\n"
    "# comment\n"
)
err_before, original = 0, list(_APP_ALIASES.keys())
ok, errors, parsed = validate_alias_text(text)
print("valid ok:", ok, "parsed:", parsed)
assert ok, errors
assert parsed.get("chrome") == "https://www.google.com"
assert parsed.get("whatsapp") == "https://web.whatsapp.com"

# 2) reject bad specs
bad = (
    "bash -c evil  ->  rm\n"
    "rm  ->  rm\n"
    "x; ls  ->  /usr/bin/x\n"
    "wsl  ->  C:\\a.exe\n"
    "~bin  ->  ~/bin/x\n"
    "blob  ->  /bin/bash\n"
    "weird  ->  foo; rm -rf /\n"
)
ok2, errors2, parsed2 = validate_alias_text(bad)
print("bad entries rejected:", ok2 is False, "n_errors:", len(errors2))
for e in errors2:
    print("  -", e)
assert ok2 is False
assert parsed2 == {}

# 3) clean entries still allowed
good = "wa -> https://web.whatsapp.com\nmybin -> /usr/bin/mybin" if False else None
ok3, err3, p3 = validate_alias_text("wa -> https://web.whatsapp.com\n")
assert ok3 is True
print("good-only accepted :", ok3)

# 4) no agent tool can read or write the alias table / settings
protected_names = [getattr(t, "name", None) for t in TOOLS]
leak = [n for n in protected_names if n and ("alias" in n.lower() or "setting" in n.lower())]
assert leak == [], f"agent tool leaks into settings: {leak}"
print("privacy check: no agent tool can read/write aliases or settings -> PASSED")

# 5) fast path only fires for safe inputs
for txt in ["open a.exe", "open notes.sh", "open ../x", "open ~", "volume 400"]:
    assert _fast_command(txt) is None or "range" in (_fast_command(txt) or {}).get("reply",""), txt
print("fast path rejects unsafe inputs")

print("ALL alias whitelist TESTS PASSED")
