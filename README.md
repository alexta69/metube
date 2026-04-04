# MeTube

![Build Status](https://github.com/alexta69/metube/actions/workflows/main.yml/badge.svg)
![Docker Pulls](https://img.shields.io/docker/pulls/alexta69/metube.svg)

MeTube is a self-hosted web UI for `yt-dlp`, for downloading media from YouTube and [dozens of other sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

Key capabilities:
* Download videos, audio, captions, and thumbnails from a browser UI.
* Download playlists and channels, with configurable output and download options.
* Subscribe to channels and playlists, periodically check for new items, and queue new uploads automatically.

![screenshot1](https://github.com/alexta69/metube/raw/master/screenshot.gif)

## 🐳 Run using Docker

```bash
docker run -d -p 8081:8081 -v /path/to/downloads:/downloads ghcr.io/alexta69/metube
```

## 🐳 Run using docker-compose

```yaml
services:
  metube:
    image: ghcr.io/alexta69/metube
    container_name: metube
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      - /path/to/downloads:/downloads
```

## ⚙️ Configuration via environment variables

Certain values can be set via environment variables, using the `-e` parameter on the docker command line, or the `environment:` section in docker-compose.

### ⬇️ Download Behavior

* __MAX_CONCURRENT_DOWNLOADS__: Maximum number of simultaneous downloads allowed. For example, if set to `5`, then at most five downloads will run concurrently, and any additional downloads will wait until one of the active downloads completes. Defaults to `3`. 
* __DELETE_FILE_ON_TRASHCAN__: if `true`, downloaded files are deleted on the server, when they are trashed from the "Completed" section of the UI. Defaults to `false`.
* __DEFAULT_OPTION_PLAYLIST_ITEM_LIMIT__: Maximum number of playlist items that can be downloaded. Defaults to `0` (no limit).
* __SUBSCRIPTION_DEFAULT_CHECK_INTERVAL__: Default minutes between automatic checks for each subscription. Defaults to `60`.
* __SUBSCRIPTION_SCAN_PLAYLIST_END__: Maximum playlist/channel entries to fetch per subscription check (newest-first). Defaults to `50`.
* __SUBSCRIPTION_MAX_SEEN_IDS__: Cap on stored video IDs per subscription to limit state file growth. Defaults to `50000`.
* __CLEAR_COMPLETED_AFTER__: Number of seconds after which completed (and failed) downloads are automatically removed from the "Completed" list. Defaults to `0` (disabled).

### 📁 Storage & Directories

* __DOWNLOAD_DIR__: Path to where the downloads will be saved. Defaults to `/downloads` in the Docker image, and `.` otherwise.
* __AUDIO_DOWNLOAD_DIR__: Path to where audio-only downloads will be saved, if you wish to separate them from the video downloads. Defaults to the value of `DOWNLOAD_DIR`.
* __CUSTOM_DIRS__: Whether to enable downloading videos into custom directories within the __DOWNLOAD_DIR__ (or __AUDIO_DOWNLOAD_DIR__). When enabled, a dropdown appears next to the Add button to specify the download directory. Defaults to `true`.
* __CREATE_CUSTOM_DIRS__: Whether to support automatically creating directories within the __DOWNLOAD_DIR__ (or __AUDIO_DOWNLOAD_DIR__) if they do not exist. When enabled, the download directory selector supports free-text input, and the specified directory will be created recursively. Defaults to `true`.
* __CUSTOM_DIRS_EXCLUDE_REGEX__: Regular expression to exclude some custom directories from the dropdown. Empty regex disables exclusion. Defaults to `(^|/)[.@].*$`, which means directories starting with `.` or `@`.
* __DOWNLOAD_DIRS_INDEXABLE__: If `true`, the download directories (__DOWNLOAD_DIR__ and __AUDIO_DOWNLOAD_DIR__) are indexable on the web server. Defaults to `false`.
* __STATE_DIR__: Path to where MeTube will store its persistent state files (`queue.json`, `pending.json`, `completed.json`, `subscriptions.json`). Defaults to `/downloads/.metube` in the Docker image, and `.` otherwise.
* __TEMP_DIR__: Path where intermediary download files will be saved. Defaults to `/downloads` in the Docker image, and `.` otherwise.
  * Set this to an SSD or RAM filesystem (e.g., `tmpfs`) for better performance.
  * __Note__: Using a RAM filesystem may prevent downloads from being resumed.
* __CHOWN_DIRS__: If `false`, ownership of `DOWNLOAD_DIR`, `STATE_DIR`, and `TEMP_DIR` (and their contents) will not be set on container start. Ensure user under which MeTube runs has necessary access to these directories already. Defaults to `true`.

### 📝 File Naming & yt-dlp

* __OUTPUT_TEMPLATE__: The template for the filenames of the downloaded videos, formatted according to [this spec](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#output-template). Defaults to `%(title)s.%(ext)s`.
* __OUTPUT_TEMPLATE_CHAPTER__: The template for the filenames of the downloaded videos when split into chapters via postprocessors. Defaults to `%(title)s - %(section_number)s %(section_title)s.%(ext)s`.
* __OUTPUT_TEMPLATE_PLAYLIST__: The template for the filenames of the downloaded videos when downloaded as a playlist. Defaults to `%(playlist_title)s/%(title)s.%(ext)s`. Set to empty to use `OUTPUT_TEMPLATE` instead.
* __OUTPUT_TEMPLATE_CHANNEL__: The template for the filenames of the downloaded videos when downloaded as a channel. Defaults to `%(channel)s/%(title)s.%(ext)s`. Set to empty to use `OUTPUT_TEMPLATE` instead.
* __YTDL_OPTIONS__: Additional options to pass to yt-dlp, as a JSON object. See [Configuring yt-dlp options](#%EF%B8%8F-configuring-yt-dlp-options) for details, examples, and available options reference.
* __YTDL_OPTIONS_FILE__: Path to a JSON file containing yt-dlp options. Monitored and reloaded automatically on changes. See [Configuring yt-dlp options](#%EF%B8%8F-configuring-yt-dlp-options).
* __YTDL_OPTIONS_PRESETS__: Named bundles of yt-dlp options, selectable per download in the UI. See [Configuring yt-dlp options](#%EF%B8%8F-configuring-yt-dlp-options) for format and examples.
* __YTDL_OPTIONS_PRESETS_FILE__: Path to a JSON file containing presets. Monitored and reloaded automatically on changes. See [Configuring yt-dlp options](#%EF%B8%8F-configuring-yt-dlp-options).
* __ALLOW_YTDL_OPTIONS_OVERRIDES__: Whether to show a free-text field in the UI for per-download yt-dlp option overrides. Defaults to `false`. See [Configuring yt-dlp options](#%EF%B8%8F-configuring-yt-dlp-options) for details and security considerations.

### 🌐 Web Server & URLs

* __HOST__: The host address the web server will bind to. Defaults to `0.0.0.0` (all interfaces).
* __PORT__: The port number the web server will listen on. Defaults to `8081`.
* __URL_PREFIX__: Base path for the web server (for use when hosting behind a reverse proxy). Defaults to `/`.
* __PUBLIC_HOST_URL__: Base URL for the download links shown in the UI for completed files. By default, MeTube serves them under its own URL. If your download directory is accessible on another URL and you want the download links to be based there, use this variable to set it.
* __PUBLIC_HOST_AUDIO_URL__: Same as PUBLIC_HOST_URL but for audio downloads.
* __HTTPS__: Use `https` instead of `http` (__CERTFILE__ and __KEYFILE__ required). Defaults to `false`.
* __CERTFILE__: HTTPS certificate file path.
* __KEYFILE__: HTTPS key file path.
* __ROBOTS_TXT__: A path to a `robots.txt` file mounted in the container.

### 🏠 Basic Setup

* __PUID__: User under which MeTube will run. Defaults to `1000` (legacy `UID` also supported).
* __PGID__: Group under which MeTube will run. Defaults to `1000` (legacy `GID` also supported).
* __UMASK__: Umask value used by MeTube. Defaults to `022`.
* __DEFAULT_THEME__: Default theme to use for the UI, can be set to `light`, `dark`, or `auto`. Defaults to `auto`.
* __LOGLEVEL__: Log level, can be set to `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, or `NONE`. Defaults to `INFO`. 
* __ENABLE_ACCESSLOG__: Whether to enable access log. Defaults to `false`.

## 🎛️ Configuring yt-dlp options

MeTube lets you customize how [yt-dlp](https://github.com/yt-dlp/yt-dlp) behaves at three levels, from broadest to most specific:

1. **Global options** — apply to every download by default.
2. **Presets** — named bundles of options that users can pick per download from the UI.
3. **Per-download overrides** — free-form options entered in the UI for a single download.

When a download starts, these layers are combined in order. If the same option appears in more than one layer, the more specific one wins: per-download overrides beat presets, and presets beat global options.

### Option format

yt-dlp options in MeTube are expressed as JSON objects. The keys are yt-dlp API option names, which roughly correspond to command-line flags with dashes replaced by underscores. For example, the command-line flag `--embed-thumbnail` becomes `"embed_thumbnail": true` in JSON.

> **Tip:** Some command-line flags don't have a direct single-key equivalent — for instance, `--recode-video` must be expressed via `"postprocessors"`. A full list of available API options can be found [in the yt-dlp source](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L224), and [this conversion script](https://github.com/yt-dlp/yt-dlp/blob/master/devscripts/cli_to_api.py) can help translate command-line flags to their API equivalents.

### Global options

Global options form the baseline for every download. There are two ways to define them, and you can use either or both:

**Inline via environment variable** (`YTDL_OPTIONS`) — pass a JSON object directly:

```yaml
environment:
  - 'YTDL_OPTIONS={"writesubtitles": true, "subtitleslangs": ["en", "de"], "updatetime": false, "embed_thumbnail": true}'
```

**Via a JSON file** (`YTDL_OPTIONS_FILE`) — mount a file into the container and point to it:

```yaml
volumes:
  - /path/to/ytdl-options.json:/config/ytdl-options.json
environment:
  - YTDL_OPTIONS_FILE=/config/ytdl-options.json
```

where `ytdl-options.json` contains:

```json
{
  "writesubtitles": true,
  "subtitleslangs": ["en", "de"],
  "updatetime": false,
  "embed_thumbnail": true
}
```

The file is monitored for changes and reloaded automatically — no container restart needed. If you use both methods and they define the same key, the **file takes precedence**.

### Presets

Presets let you define named bundles of options that appear in the web UI under **Advanced Options** as "Option Presets". Users can select one or more presets per download, making it easy to apply common option combinations without editing global settings.

Like global options, presets can be set inline or via a file:

* `YTDL_OPTIONS_PRESETS` — a JSON object where each key is a preset name and its value is a set of yt-dlp options.
* `YTDL_OPTIONS_PRESETS_FILE` — path to a JSON file containing presets, monitored and reloaded on changes.

If both are used and they define a preset with the same name, the **file's version takes precedence**.

**Example** — a presets file defining three presets:

```json
{
  "sponsorblock": {
    "postprocessors": [
      { "key": "SponsorBlock", "categories": ["sponsor", "selfpromo", "interaction"] },
      { "key": "ModifyChapters", "remove_sponsor_segments": ["sponsor", "selfpromo", "interaction"] }
    ]
  },
  "embed-subs": {
    "writesubtitles": true,
    "writeautomaticsub": true,
    "subtitleslangs": ["en", "de"],
    "postprocessors": [{ "key": "FFmpegEmbedSubtitle" }]
  },
  "limit-rate": {
    "ratelimit": 5000000
  }
}
```

This makes three presets available in the UI:
* **sponsorblock** — strips sponsor, self-promo, and interaction segments from videos.
* **embed-subs** — downloads English and German subtitles and embeds them into the video file.
* **limit-rate** — caps download speed to ~5 MB/s.

When multiple presets are selected for a download, they are applied in order. If two presets set the same option, the later one wins.

### Per-download overrides

For one-off tweaks, MeTube can expose a free-text JSON field in the UI ("Custom yt-dlp Options") where users type yt-dlp options that apply only to that single download. This is disabled by default:

```yaml
environment:
  - ALLOW_YTDL_OPTIONS_OVERRIDES=true
```

Once enabled, the field appears under **Advanced Options**. Any options entered there take the highest priority, overriding both global options and selected presets.

> **⚠️ Security note:** Enabling this allows arbitrary yt-dlp API options to be supplied by anyone with access to the UI. Depending on the options used, this may enable arbitrary command execution inside the container. Enable only in trusted environments.

### How the layers combine

When a download starts, the final set of yt-dlp options is built in this order:

1. Start with **global options** (`YTDL_OPTIONS` / `YTDL_OPTIONS_FILE`).
2. Apply each selected **preset** in order (later presets overwrite earlier ones for conflicting keys).
3. Apply any **per-download overrides** on top (overwrite everything else for conflicting keys).

**Example:** Suppose your global options set `"writesubtitles": false`, but you select a preset that sets `"writesubtitles": true`. Subtitles will be written for that download because the preset overrides the global setting. If you additionally enter `{"writesubtitles": false}` in the per-download overrides field, that value wins and subtitles will not be written.

### Configuration cookbooks

The project's Wiki contains examples of useful configurations contributed by users of MeTube:
* [YTDL_OPTIONS Cookbook](https://github.com/alexta69/metube/wiki/YTDL_OPTIONS-Cookbook)
* [OUTPUT_TEMPLATE Cookbook](https://github.com/alexta69/metube/wiki/OUTPUT_TEMPLATE-Cookbook)

## 🍪 Using browser cookies

In case you need to use your browser's cookies with MeTube, for example to download restricted or private videos:

* Install in your browser an extension to extract cookies:
  * [Firefox](https://addons.mozilla.org/en-US/firefox/addon/export-cookies-txt/)
  * [Chrome](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
* Extract the cookies you need with the extension and save/export them as `cookies.txt`.
* In MeTube, open **Advanced Options** and use the **Upload Cookies** button to upload the file.
* After upload, the cookie indicator should show as active.
* Use **Delete Cookies** in the same section to remove uploaded cookies.

## 🔌 Browser extensions

Browser extensions allow right-clicking videos and sending them directly to MeTube. Please note that if you're on an HTTPS page, your MeTube instance must be behind an HTTPS reverse proxy (see below) for the extensions to work.

__Chrome:__ contributed by [Rpsl](https://github.com/rpsl). You can install it from [Google Chrome Webstore](https://chrome.google.com/webstore/detail/metube-downloader/fbmkmdnlhacefjljljlbhkodfmfkijdh) or use developer mode and install [from sources](https://github.com/Rpsl/metube-browser-extension).

__Firefox:__ contributed by [nanocortex](https://github.com/nanocortex). You can install it from [Firefox Addons](https://addons.mozilla.org/en-US/firefox/addon/metube-downloader) or get sources from [here](https://github.com/nanocortex/metube-firefox-addon).

## 📱 iOS Shortcut

[rithask](https://github.com/rithask) created an iOS shortcut to send URLs to MeTube from Safari. Enter the MeTube instance address when prompted which will be saved for later use. You can run the shortcut from Safari’s share menu. The shortcut can be downloaded from [this iCloud link](https://www.icloud.com/shortcuts/66627a9f334c467baabdb2769763a1a6).

## 🔖 Bookmarklet

[kushfest](https://github.com/kushfest) has created a Chrome bookmarklet for sending the currently open webpage to MeTube. Please note that if you're on an HTTPS page, your MeTube instance must be configured with `HTTPS` as `true` in the environment, or be behind an HTTPS reverse proxy (see below) for the bookmarklet to work.

GitHub doesn't allow embedding JavaScript as a link, so the bookmarklet has to be created manually by copying the following code to a new bookmark you create on your bookmarks bar. Change the hostname in the URL below to point to your MeTube instance.

```javascript
javascript:!function(){xhr=new XMLHttpRequest();xhr.open("POST","https://metube.domain.com/add");xhr.withCredentials=true;xhr.send(JSON.stringify({"url":document.location.href,"quality":"best"}));xhr.onload=function(){if(xhr.status==200){alert("Sent to metube!")}else{alert("Send to metube failed. Check the javascript console for clues.")}}}();
```

[shoonya75](https://github.com/shoonya75) has contributed a Firefox version:

```javascript
javascript:(function(){xhr=new XMLHttpRequest();xhr.open("POST","https://metube.domain.com/add");xhr.send(JSON.stringify({"url":document.location.href,"quality":"best"}));xhr.onload=function(){if(xhr.status==200){alert("Sent to metube!")}else{alert("Send to metube failed. Check the javascript console for clues.")}}})();
```

The above bookmarklets use `alert()` as a success/failure notification. The following will show a toast message instead:

Chrome:

```javascript
javascript:!function(){function notify(msg) {var sc = document.scrollingElement.scrollTop; var text = document.createElement('span');text.innerHTML=msg;var ts = text.style;ts.all = 'revert';ts.color = '#000';ts.fontFamily = 'Verdana, sans-serif';ts.fontSize = '15px';ts.backgroundColor = 'white';ts.padding = '15px';ts.border = '1px solid gainsboro';ts.boxShadow = '3px 3px 10px';ts.zIndex = '100';document.body.appendChild(text);ts.position = 'absolute'; ts.top = 50 + sc + 'px'; ts.left = (window.innerWidth / 2)-(text.offsetWidth / 2) + 'px'; setTimeout(function () { text.style.visibility = "hidden"; }, 1500);}xhr=new XMLHttpRequest();xhr.open("POST","https://metube.domain.com/add");xhr.send(JSON.stringify({"url":document.location.href,"quality":"best"}));xhr.onload=function() { if(xhr.status==200){notify("Sent to metube!")}else {notify("Send to metube failed. Check the javascript console for clues.")}}}();
```

Firefox:

```javascript
javascript:(function(){function notify(msg) {var sc = document.scrollingElement.scrollTop; var text = document.createElement('span');text.innerHTML=msg;var ts = text.style;ts.all = 'revert';ts.color = '#000';ts.fontFamily = 'Verdana, sans-serif';ts.fontSize = '15px';ts.backgroundColor = 'white';ts.padding = '15px';ts.border = '1px solid gainsboro';ts.boxShadow = '3px 3px 10px';ts.zIndex = '100';document.body.appendChild(text);ts.position = 'absolute'; ts.top = 50 + sc + 'px'; ts.left = (window.innerWidth / 2)-(text.offsetWidth / 2) + 'px'; setTimeout(function () { text.style.visibility = "hidden"; }, 1500);}xhr=new XMLHttpRequest();xhr.open("POST","https://metube.domain.com/add");xhr.send(JSON.stringify({"url":document.location.href,"quality":"best"}));xhr.onload=function() { if(xhr.status==200){notify("Sent to metube!")}else {notify("Send to metube failed. Check the javascript console for clues.")}}})();
```

## ⚡ Raycast extension

[dotvhs](https://github.com/dotvhs) has created an [extension for Raycast](https://www.raycast.com/dot/metube) that allows adding videos to MeTube directly from Raycast.

## 🔒 HTTPS support, and running behind a reverse proxy

It's possible to configure MeTube to listen in HTTPS mode. `docker-compose` example:

```yaml
services:
  metube:
    image: ghcr.io/alexta69/metube
    container_name: metube
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      - /path/to/downloads:/downloads
      - /path/to/ssl/crt:/ssl/crt.pem
      - /path/to/ssl/key:/ssl/key.pem
    environment:
      - HTTPS=true
      - CERTFILE=/ssl/crt.pem
      - KEYFILE=/ssl/key.pem
```

It's also possible to run MeTube behind a reverse proxy, in order to support authentication. HTTPS support can also be added in this way.

When running behind a reverse proxy which remaps the URL (i.e. serves MeTube under a subdirectory and not under root), don't forget to set the URL_PREFIX environment variable to the correct value.

If you're using the [linuxserver/swag](https://docs.linuxserver.io/general/swag) image for your reverse proxying needs (which I can heartily recommend), it already includes ready snippets for proxying MeTube both in [subfolder](https://github.com/linuxserver/reverse-proxy-confs/blob/master/metube.subfolder.conf.sample) and [subdomain](https://github.com/linuxserver/reverse-proxy-confs/blob/master/metube.subdomain.conf.sample) modes under the `nginx/proxy-confs` directory in the configuration volume. It also includes Authelia which can be used for authentication.

### 🌐 NGINX

```nginx
location /metube/ {
        proxy_pass http://metube:8081;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
}
```

Note: the extra `proxy_set_header` directives are there to make WebSocket work.

### 🌐 Apache

Contributed by [PIE-yt](https://github.com/PIE-yt). Source [here](https://gist.github.com/PIE-yt/29e7116588379032427f5bd446b2cac4).

```apache
# For putting in your Apache sites site.conf
# Serves MeTube under a /metube/ subdir (http://yourdomain.com/metube/)
<Location /metube/>
    ProxyPass http://localhost:8081/ retry=0 timeout=30
    ProxyPassReverse http://localhost:8081/
</Location>

<Location /metube/socket.io>
    RewriteEngine On
    RewriteCond %{QUERY_STRING} transport=websocket    [NC]
    RewriteRule /(.*) ws://localhost:8081/socket.io/$1 [P,L]
    ProxyPass http://localhost:8081/socket.io retry=0 timeout=30
    ProxyPassReverse http://localhost:8081/socket.io
</Location>
```

### 🌐 Caddy

The following example Caddyfile gets a reverse proxy going behind [caddy](https://caddyserver.com).

```caddyfile
example.com {
  route /metube/* {
    uri strip_prefix metube
    reverse_proxy metube:8081
  }
}
```

## 🔄 Updating yt-dlp

The engine which powers the actual video downloads in MeTube is [yt-dlp](https://github.com/yt-dlp/yt-dlp). Since video sites regularly change their layouts, frequent updates of yt-dlp are required to keep up.

There's an automatic nightly build of MeTube which looks for a new version of yt-dlp, and if one exists, the build pulls it and publishes an updated docker image. Therefore, in order to keep up with the changes, it's recommended that you update your MeTube container regularly with the latest image.

I recommend installing and setting up [watchtower](https://github.com/nicholas-fedor/watchtower) for this purpose.

## 🔧 Troubleshooting and submitting issues

Before asking a question or submitting an issue for MeTube, please remember that MeTube is only a UI for [yt-dlp](https://github.com/yt-dlp/yt-dlp). Any issues you might be experiencing with authentication to video websites, postprocessing, permissions, other `YTDL_OPTIONS` configurations which seem not to work, or anything else that concerns the workings of the underlying yt-dlp library, need not be opened on the MeTube project. In order to debug and troubleshoot them, it's advised to try using the yt-dlp binary directly first, bypassing the UI, and once that is working, importing the options that worked for you into `YTDL_OPTIONS`.

In order to test with the yt-dlp command directly, you can either download it and run it locally, or for a better simulation of its actual conditions, you can run it within the MeTube container itself. Assuming your MeTube container is called `metube`, run the following on your Docker host to get a shell inside the container:

```bash
docker exec -ti metube sh
cd /downloads
```

Once there, you can use the yt-dlp command freely.

## 💡 Submitting feature requests

MeTube development relies on code contributions by the community. The program as it currently stands fits my own use cases, and is therefore feature-complete as far as I'm concerned. If your use cases are different and require additional features, please feel free to submit PRs that implement those features. It's advisable to create an issue first to discuss the planned implementation, because in an effort to reduce bloat, some PRs may not be accepted. However, note that opening a feature request when you don't intend to implement the feature will rarely result in the request being fulfilled.

## 🛠️ Building and running locally

Make sure you have Node.js 22+ and Python 3.13 installed.

```bash
# install Angular and build the UI
cd ui
curl -fsSL https://get.pnpm.io/install.sh | sh -
pnpm install
pnpm run build
# install python dependencies
cd ..
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
# run
uv run python3 app/main.py
```

A Docker image can be built locally (it will build the UI too):

```bash
docker build -t metube .
```

Note that if you're running the server in VSCode, your downloads will go to your user's Downloads folder (this is configured via the environment in `.vscode/launch.json`).
