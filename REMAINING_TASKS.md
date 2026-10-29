# Remaining Tasks / TODO

This file lists project work still to be done.

## React app pages
- DONE: MemoryPage (`/memory`), ActivityPage (`/activity`), UsagePage (`/usage`), DocumentsPage (`/documents`) added under `web/src/pages/` and wired into `web/src/App.tsx` routes. Sidebar nav links now resolve.
- Documents page is connected to `/api/documents` for list, upload, search, reindex, and delete.
- Memory, Activity, and Usage pages use their corresponding authenticated API routes.

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
