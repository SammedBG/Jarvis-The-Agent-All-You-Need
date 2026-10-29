# Remaining Tasks / TODO

This file lists project work still to be done.

## React app pages
- Missing pages: Memory, Activity, Usage, Documents.
- Existing API routes available: `/api/memory`, `/api/activity`, `/api/usage`.
- Documents upload/list/search needs backend route check or a clear not available state.

## README and requirements
- Keep README synced with code and verified commandvs.
- Polish package/version pins in requirements lock.



- Document desktop-only package install flow on Windows.

## Failure paths testing
- Raise Playwright coverage: 401, 403, 422, 429, 500, network, empty stream, SSE error, aborted stream.

## Voice and desktop
- Make wake word setup reproducible on Python 3.12.
- Install/report system audio dependencies clearly.
- Validate hotkey behavior on Linux Wayland and tray fallback.

## Known product limits
- Native installer packaging.
- PWA install polish.
- Multi-user role policies beyond owner.
- Custom model providers outside allowlist.
