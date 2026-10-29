"""Fail if Streamlit pages render CSS rules as visible markdown text."""
import os
os.environ.setdefault("JARVIS_DB", "/tmp/opencode/css_leak_test.db")

import re

from streamlit.testing.v1 import AppTest

pages = None
ROOT = "/home/rokkun-23/Desktop/Agnet_Example"

PAGES = [None, "app_pages/chat.py", "app_pages/today.py", "app_pages/memory.py",
         "app_pages/activity.py", "app_pages/tasks.py", "app_pages/documents.py",
         "app_pages/settings.py", "app_pages/usage.py"]

# Patterns that look like stray CSS rule text (raw text, not <style>-wrapped)
css_prop = re.compile(r"\{[^{}]*?(border-radius|background|padding|color):\s*[^{};]+;")
css_value = re.compile(r"\b(?:margin|padding|font-size|line-height)\s*:\s*[^;]+;", re.I)


def _all_rendered_markdown(at):
    out = []
    for el in at.markdown:
        try:
            out.append(el.value)
        except Exception:
            pass
    return out


def main():
    failures = []
    for p in PAGES:
        at = AppTest.from_file(ROOT + "/ui.py", default_timeout=300)
        if p:
            at.switch_page(p)
        at.run()
        for v in _all_rendered_markdown(at):
            if "{" in v and ";" in v and ("border-radius" in v.lower() or "background:" in v.lower() or "padding:" in v.lower()):
                # check after stripping legitimate markup
                if css_prop.search(v) or css_value.search(v):
                    failures.append((p or "entry", v[:200]))
        if at.error:
            failures.append((p or "entry", "RUN_ERROR " + str(at.error)))
    if failures:
        print("FAILED:")
        for p, v in failures:
            print(p, "::", v)
        raise SystemExit(1)
    print("ALL PAGES CSS LEAK TEST PASSED")


if __name__ == "__main__":
    main()
