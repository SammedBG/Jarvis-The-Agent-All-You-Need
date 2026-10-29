"""
mail.py - optional email digest for the morning briefing.

Strictly READ-ONLY. Uses IMAP over SSL with a Gmail "app password" (16 chars).
Configure in .env:
    GMAIL_ADDRESS=you@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
    GMAIL_IMAP_HOST=imap.gmail.com   (optional, defaults to gmail)
    GMAIL_IMAP_PORT=993               (optional)

If the env is missing it's a no-op with a short message, so the briefing still
works without email.
"""
from __future__ import annotations

import email as _email
import imaplib
import os
import re
from datetime import datetime
from email.utils import parseaddr
from langchain_core.tools import tool

MAX_DIGEST = 8


def configured() -> bool:
    return bool(os.getenv("GMAIL_ADDRESS", "") and os.getenv("GMAIL_APP_PASSWORD", ""))


@tool
def check_email(limit: int = 5, only_unread: bool = True) -> str:
    """Read-only glance at the inbox: count + the subjects/senders of the
    most recent unread (or all) messages, plus whether anything is important."""
    limit = max(1, min(int(limit or 5), MAX_DIGEST))
    if not configured():
        return ("Email not configured. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD "
                "in .env (Gmail: turn on 2FA, then create an App Password).")
    host = os.getenv("GMAIL_IMAP_HOST", "imap.gmail.com")
    port = int(os.getenv("GMAIL_IMAP_PORT", "993"))
    user = os.getenv("GMAIL_ADDRESS", "")
    pwd = os.getenv("GMAIL_APP_PASSWORD", "")
    try:
        with imaplib.IMAP4_SSL(host, port, timeout=25) as imap:
            imap.login(user, pwd)
            imap.select("INBOX")
            crit = "UNSEEN" if only_unread else "ALL"
            ok, data = imap.search(None, crit)
            if ok != "OK" or not data or not data[0]:
                imap.logout()
                return "Inbox is empty of unread mail."
            ids = data[0].split()
            total_unread = len(ids)
            sample_ids = ids[-limit:]
            lines = []
            for mid in reversed(sample_ids):
                try:
                    ok, d = imap.fetch(mid, "(RFC822.HEADER)")
                    if ok != "OK" or not d or d[0] is None:
                        continue
                    raw = d[0][1] if isinstance(d[0], tuple) else d[0]
                    msg = _email.message_from_bytes(raw if isinstance(raw, (bytes, bytearray)) else str(raw).encode())
                    sender = parseaddr(msg.get("From", ""))[1] or msg.get("From", "")
                    subj = msg.get("Subject", "(no subject)")
                    # trim noisy Unicode for the plain-text briefing
                    subj = re.sub(r"\s+", " ", subj).strip()[:90]
                    lines.append(f"- From {sender}: {subj}")
                except Exception:
                    continue
            imap.logout()
            if not lines:
                lines.append("(unread subjects unreadable)")
            return (f"Inbox unread: {total_unread} "
                    f"(showing {len(lines)} most recent).\n" + "\n".join(lines))
    except Exception as e:
        return f"Email check failed (not configured or network error): {e}"