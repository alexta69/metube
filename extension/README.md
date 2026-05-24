# MeTube Clip Marker

Chrome extension (Manifest V3) — mark clip times on **any page with a `<video>` element** and queue them to your MeTube instance.

## Requirements

- MeTube with **batch clips** support (`POST /add-batch`) and single-clip `POST /add`
- `CORS_ALLOWED_ORIGINS=*` on the MeTube server

## Install (unpacked)

1. Open `chrome://extensions/`
2. Enable **Developer mode**
3. **Load unpacked** → select this `extension/` folder
4. Open **Extension options** → set your MeTube URL (default `http://localhost:8081/`)

## Usage

1. Open a page with a video player and reload the tab after installing or updating the extension.
2. Use the floating bar at the bottom-right (**Start** / **End**).
3. Open the extension popup → **Queue clips** or **Queue merged** (merge needs at least two clips).

Clip times are stored per page until you remove them or close the browser.
