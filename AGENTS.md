# Agent Guidelines

## Project scope — read this before planning a feature

MeTube's contract is: give it a URL, it runs yt-dlp well, and correct files appear.
The maintainer holds a deliberate line on what belongs inside that contract, and PRs
on the wrong side of it are declined **regardless of code quality**. Check your plan
against this line before writing any code.

**In scope — improving the write itself:**

- Features that make the file yt-dlp writes at download time come out more correct,
  using only data the extractor already provides (e.g. filling a missing album-artist
  tag from the extractor's own metadata).
- Surfacing functionality yt-dlp itself owns and maintains as first-class UI options
  (e.g. a SponsorBlock toggle that just passes yt-dlp postprocessor params).
- Download queue, subscriptions, output templates, and UI improvements to the
  download workflow.

**Out of scope — managing files after they exist:**

- Tag editors, metadata dialogs, or any workflow that rewrites files after the
  download has finished. This holds even for slimmed-down versions.
- Lookups against external metadata services (iTunes, Deezer, MusicBrainz, etc.).
  More broadly: any new dependency on a third-party API, or new network egress from
  self-hosted instances, beyond what yt-dlp itself performs.
- Library organization: moving/renaming existing files into Artist/Album layouts,
  watch-folder processing, and similar media-manager features. Dedicated tools
  (beets, MusicBrainz Picard, Lidarr) do this properly; the README points users
  to them.

**Corollaries that shape borderline PRs:**

- Site-specific intelligence (parsing playlist-ID prefixes, URL path conventions,
  and other platform internals) is extractor work and belongs upstream in yt-dlp,
  not re-implemented here — it silently breaks when the platform changes and
  MeTube would own the breakage.
- Prefer enriching yt-dlp's info dict and letting its existing pipeline
  (FFmpegMetadata etc.) do the writing, over adding custom per-format tag-writing
  code to MeTube.
- Supplemental processing must never fail a download that otherwise succeeded:
  warn and continue, don't raise.
- Keep feature scope minimal on first submission. A hardcoded sensible default
  beats a configuration surface; follow-ups can add options when users actually
  ask. PRs that bundle several "reasonable next steps" invite rejection of the
  whole.

If a feature idea fails this test, the accepted alternative is usually a README
section documenting how to pair MeTube with the right dedicated tool.

## README.md size constraint

The README.md is synced to Docker Hub, which has a **25,000 character limit**.
Any change to README.md **must** keep the file under 25,000 characters (`wc -c README.md`).
If an addition would exceed the limit, trim existing prose elsewhere — prefer tightening verbose descriptions over removing sections.

## Tech stack

- **Backend:** Python 3.13+, aiohttp, python-socketio 5.x, yt-dlp
- **Frontend:** Angular 22, TypeScript, Bootstrap 5, SASS, ngx-socket-io
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

Gotchas:

- Backend tests must run **from the repo root**: `main.py` resolves the static-assets
  path relative to the cwd, and several test modules import `main`. Running from
  `app/` makes five test modules fail to import.
- The frontend must be **built before** running backend tests (same reason — the
  assets at `ui/dist/metube/browser` must exist). The command order above is
  load-bearing.
- `app/tests/test_ytdl_utils.py` stubs `yt_dlp` at import time. Run standalone,
  two tests fail with `AttributeError: <module 'yt_dlp'> does not have the
  attribute 'YoutubeDL'`; under the full suite the real module is imported first
  and they pass. This is a known quirk, not a bug to fix in the code under test.

Every non-markdown push to master builds multi-arch Docker images and cuts a dated
release the same day. **Master is continuously released** — a PR must be
release-ready exactly as merged; there is no stabilization window for follow-up
fixes.

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
- Frontend components use OnPush change detection: subscribe callbacks must call `cdr.markForCheck()`.
- State is persisted as JSON files via `AtomicJsonStore` in `app/state_store.py`.
- Persisted state stays compact: the completed queue deliberately drops bulky entry data (see `_compact_persisted_entry` in `app/ytdl.py`). Don't expand what gets persisted without discussion.
- Custom yt-dlp postprocessors added to `ytdl_params['postprocessors']` run in **list order** within a stage. When combining postprocessors, mirror the ordering the yt-dlp CLI would produce (e.g. sponsor-segment removal before chapter splitting).
- No pre-commit hooks — linting and tests are enforced in CI only.

## Checklist: adding a per-download option

New options on the download form (the `split_by_chapters` pattern) need **all** of
these pieces — the last three are the ones commonly missed:

1. `parse_download_options` in `app/main.py`.
2. A field on `DownloadInfo` in `app/ytdl.py`.
3. A `hasattr` backfill in `DownloadInfo.__setstate__` for old persisted records.
4. The safe-deserialization field list in `app/ytdl.py`.
5. UI form control + cookie persistence in `ui/src/app/app.ts` / `app.html`, and
   the payload in `downloads.service.ts` (plus its spec).
6. The redownload path in `app.ts`, so retries carry the option.
7. If the option makes sense for unattended downloads: threading through
   `app/subscriptions.py` (`SubscriptionInfo` field, serializer, add/update
   routes, the enqueue call) — or a note in the PR that it's deliberately
   direct-downloads-only.

## Security invariants

User input and extractor-provided metadata (titles, playlist names, URLs) are
untrusted. Use the existing guards instead of hand-rolling:

- User-submitted URLs go through the SSRF guard (see `test_url_guard.py` for the
  expected behavior).
- Anything that becomes a filesystem path goes through `_is_within_directory` and
  `_sanitize_path_component` in `app/ytdl.py` — including values that arrive via
  yt-dlp metadata, which sites can influence.
