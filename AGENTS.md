# Agent Guidelines

## README.md size constraint

The README.md is synced to Docker Hub, which has a **25,000 character limit**.
Any change to README.md **must** keep the file under 25,000 characters (`wc -c README.md`).
If an addition would exceed the limit, trim existing prose elsewhere — prefer tightening verbose descriptions over removing sections.

## Tech stack

- **Backend:** Python 3.13+, aiohttp, python-socketio 5.x, yt-dlp
- **Frontend:** Angular 21, TypeScript, Bootstrap 5, SASS, ngx-socket-io
- **Package managers:** uv (Python), pnpm (frontend)
- **Container:** Multi-stage Docker (Node builder + Python runtime), multi-arch (amd64/arm64)

## Build & test commands

```bash
# Frontend (run from ui/)
pnpm install --frozen-lockfile
pnpm run lint
pnpm run build
pnpm exec ng test --watch=false

# Backend (run from repo root)
uv sync --frozen --group dev
python -m compileall app
uv run pytest app/tests/
```

All of these run in CI (`.github/workflows/main.yml`) on every push to master and must pass.

## Code style

Follow `.editorconfig`:
- Python: 4-space indent
- Everything else (TypeScript, YAML, JSON, HTML): 2-space indent
- UTF-8, LF line endings, trim trailing whitespace, final newline

Frontend additionally uses ESLint (`ui/eslint.config.js`) and Prettier (config in `ui/package.json`: `printWidth=100`, `singleQuote=true`).

## Project structure

```
app/main.py          — HTTP server, Socket.IO events, REST API routes, Config class
app/ytdl.py          — Download queue logic, yt-dlp integration
app/subscriptions.py — Channel/playlist subscription manager
app/state_store.py   — JSON-based persistent storage with atomic writes
app/dl_formats.py    — Video/audio codec/quality mapping
app/tests/           — pytest tests (asyncio_mode=auto)
ui/src/app/          — Angular standalone components (no NgModules)
```

## Key conventions

- Backend configuration lives in the `Config` class in `app/main.py` with env-var defaults in `_DEFAULTS`. New env vars go there.
- Real-time communication uses Socket.IO events, not REST polling.
- Frontend uses standalone Angular components with `inject()` for DI, RxJS Subjects for state, and `takeUntilDestroyed()` for cleanup.
- State is persisted as JSON files via `AtomicJsonStore` in `app/state_store.py`.
- No pre-commit hooks — linting and tests are enforced in CI only.
