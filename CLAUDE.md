# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MeTube is a web GUI for yt-dlp (YouTube downloader) with playlist support. It consists of:

- **Backend**: Python 3.13 Flask/aiohttp server (`app/` directory) that handles yt-dlp operations
- **Frontend**: Angular application (`ui/` directory) providing the web interface
- **Architecture**: Real-time WebSocket communication using Socket.IO for download status updates

## Development Commands

### Frontend (Angular)
```bash
cd ui
npm install              # Install dependencies
npm run start           # Development server (ng serve)
npm run build           # Production build (ng build)
npm run test            # Run tests (ng test)
npm run lint            # TSLint (ng lint)
npm run e2e             # End-to-end tests (ng e2e)
```

### Backend (Python)
```bash
# Install Python dependencies
pip3 install pipenv
pipenv install

# Run development server
pipenv run python3 app/main.py

# Run with pylint (for development)
pipenv install --dev  # Installs pylint
pipenv run pylint app/
```

### Full Local Development
```bash
# 1. Build the UI first
cd ui
npm install
node_modules/.bin/ng build

# 2. Install and run Python backend
cd ..
pip3 install pipenv
pipenv install
pipenv run python3 app/main.py
```

## Code Architecture

### Backend Structure (`app/`)
- **`main.py`**: Main aiohttp server with Socket.IO, handles HTTP routes and WebSocket events
- **`ytdl.py`**: Core download queue management and yt-dlp integration
  - `DownloadQueue`: Manages download lifecycle, supports sequential/concurrent/limited modes
  - `Download`: Individual download process management with multiprocessing
  - `PersistentQueue`: Shelve-based persistence for queue state
- **`dl_formats.py`**: Format and quality selection logic for different video/audio formats

### Frontend Structure (`ui/src/app/`)
- **`app.component.ts`**: Main application component handling UI interactions and download management
- **`downloads.service.ts`**: Service managing WebSocket communication and download state
- **`metube-socket.ts`**: Socket.IO client wrapper
- **`formats.ts`**: Frontend format/quality definitions matching backend

### Key Integration Points
- **WebSocket Events**: `added`, `updated`, `completed`, `canceled`, `cleared` for real-time updates
- **HTTP Endpoints**: `/add`, `/delete`, `/start`, `/history` for download operations
- **State Persistence**: Queue, completed, and pending downloads persisted using Python shelve
- **Download Modes**: Sequential, concurrent, or limited concurrent downloads configurable via `DOWNLOAD_MODE`

### Configuration
The application uses environment variables extensively (see README.md). Key configs:
- `DOWNLOAD_DIR`, `AUDIO_DOWNLOAD_DIR`: Download destinations
- `YTDL_OPTIONS`: Custom yt-dlp options (JSON format)
- `DOWNLOAD_MODE`: Sequential/concurrent/limited download execution
- `MAX_CONCURRENT_DOWNLOADS`: Concurrency limit for limited mode

### VS Code Configuration
The `.vscode/launch.json` provides a "Python: MeTube" debug configuration that:
- Sets appropriate download directories for Windows/macOS
- Uses integrated terminal for better debugging experience

### Code Style
- **Frontend**: Uses TSLint with Angular-specific rules, prefers single quotes, 140 character line limit
- **Backend**: Uses standard Python conventions, pylint available for development

## Testing
- Frontend tests use Angular's Karma/Jasmine setup
- End-to-end tests use Protractor
- No specific backend test framework configured

## Docker Support
The project includes full Docker support with multi-stage builds that handle both frontend build and backend setup automatically.