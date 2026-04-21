# MeTube

![Build Status](https://github.com/alexta69/metube/actions/workflows/main.yml/badge.svg)
![Docker Pulls](https://img.shields.io/docker/pulls/alexta69/metube.svg)

Self-hosted web UI for [yt-dlp](https://github.com/yt-dlp/yt-dlp) — download media from YouTube and [hundreds of other sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

![screenshot](https://github.com/alexta69/metube/raw/master/screenshot.gif)

## Features

- Download videos, audio, captions, and thumbnails from a browser UI
- Download playlists and channels with customizable options
- Subscribe to channels/playlists — auto-queue new uploads
- Real-time progress via WebSocket
- Dark/light theme support

## Quick Start

\\\ash
docker run -d -p 8081:8081 -v /path/to/downloads:/downloads ghcr.io/alexta69/metube
\\\

Access at **http://localhost:8081**

### docker-compose

\\\yaml
services:
  metube:
    image: ghcr.io/alexta69/metube
    ports:
      - "8081:8081"
    volumes:
      - ./downloads:/downloads
\\\

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| \DOWNLOAD_DIR\ | Where files are saved | \/downloads\ |
| \MAX_CONCURRENT_DOWNLOADS\ | Simultaneous downloads | \3\ |
| \PORT\ | Web server port | \8081\ |
| \HOST\ | Bind address | \
