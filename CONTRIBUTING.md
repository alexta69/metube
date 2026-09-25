# Contributing to MeTube

Feature requests and pull requests are both welcome.

## Before you write code

MeTube's scope is deliberately narrow: **it downloads well, and stops once the file
is written.**

- **Welcome:** features that improve the download itself — the queue, subscriptions,
  output templates, the download form, and first-class UI for things yt-dlp already
  does.
- **Out of scope, regardless of implementation quality:** managing files after they
  exist — tag editors, lookups against metadata services, library organization.
  Dedicated tools do this properly (beets, MusicBrainz Picard, Lidarr).
- **Belongs in yt-dlp:** site support and site-specific logic. Request it
  [upstream](https://github.com/yt-dlp/yt-dlp/issues).

The full policy, with the reasoning for borderline cases, is in
[AGENTS.md](AGENTS.md#project-scope--read-this-before-planning-a-feature).

Then:

1. Check the [wiki](https://github.com/alexta69/metube/wiki) — many requests are
   already a configuration recipe — and the "Already decided" list in the
   [feature request form](https://github.com/alexta69/metube/issues/new?template=feature_request.yml).
2. For a change that isn't obvious, open an issue or a discussion about the
   approach before writing code.
3. Keep a pull request minimal: one feature, with a sensible default rather than a
   new setting where possible. Follow-ups can add options once users ask for them.

`master` is released continuously — every merge ships the same day — so a pull
request must be release-ready exactly as merged.

## Building and running locally

You need Node.js 22+ and Python 3.13.

```bash
# install Angular and build the UI
cd ui
curl -fsSL https://get.pnpm.io/install.sh | sh -
pnpm install
pnpm run build
# install Python dependencies
cd ..
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
# run
uv run python3 app/main.py
```

A Docker image can be built locally (it builds the UI too):

```bash
docker build -t metube .
```

When running the server from VS Code, downloads go to your user's Downloads folder
(configured in `.vscode/launch.json`).

## Checks

CI runs these on every push, and they must pass. Build the UI first, and run the
backend tests from the repository root.

```bash
# from ui/
pnpm run lint
pnpm exec ng test --watch=false

# from the repository root
uv sync --frozen --group dev
uv run pytest app/tests/
```

## Documentation

Documentation lives in three places, and a change goes where its kind of content
lives:

- **[README.md](README.md)** — what MeTube is, the quick start, and the environment
  variable reference: one table row per variable, a sentence or two at most. A new
  environment variable gets its row in the same pull request that adds it. The README
  is also the Docker Hub page, which caps it at 25,000 bytes, so anything that needs
  more room goes in the wiki and is linked from the row.
- **The [wiki](https://github.com/alexta69/metube/wiki)** — guides, recipes,
  integrations, and troubleshooting. GitHub wikis don't take pull requests: to add or
  fix a page, open an issue with the text, and it will be added with attribution.
- **This file** — how to contribute and build.
