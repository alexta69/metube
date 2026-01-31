# MeTube

![Build Status](https://github.com/alexta69/metube/actions/workflows/main.yml/badge.svg)
![Docker Pulls](https://img.shields.io/docker/pulls/alexta69/metube.svg)

Web GUI for youtube-dl (using the [yt-dlp](https://github.com/yt-dlp/yt-dlp) fork) with playlist support. Allows you to download videos from YouTube and [dozens of other sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

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

### 📁 Storage & Directories

* __DOWNLOAD_DIR__: Path to where the downloads will be saved. Defaults to `/downloads` in the Docker image, and `.` otherwise.
* __AUDIO_DOWNLOAD_DIR__: Path to where audio-only downloads will be saved, if you wish to separate them from the video downloads. Defaults to the value of `DOWNLOAD_DIR`.
* __CUSTOM_DIRS__: Whether to enable downloading videos into custom directories within the __DOWNLOAD_DIR__ (or __AUDIO_DOWNLOAD_DIR__). When enabled, a dropdown appears next to the Add button to specify the download directory. Defaults to `true`.
* __CREATE_CUSTOM_DIRS__: Whether to support automatically creating directories within the __DOWNLOAD_DIR__ (or __AUDIO_DOWNLOAD_DIR__) if they do not exist. When enabled, the download directory selector supports free-text input, and the specified directory will be created recursively. Defaults to `true`.
* __CUSTOM_DIRS_EXCLUDE_REGEX__: Regular expression to exclude some custom directories from the dropdown. Empty regex disables exclusion. Defaults to `(^|/)[.@].*$`, which means directories starting with `.` or `@`.
* __DOWNLOAD_DIRS_INDEXABLE__: If `true`, the download directories (__DOWNLOAD_DIR__ and __AUDIO_DOWNLOAD_DIR__) are indexable on the web server. Defaults to `false`.
* __STATE_DIR__: Path to where the queue persistence files will be saved. Defaults to `/downloads/.metube` in the Docker image, and `.` otherwise.
* __TEMP_DIR__: Path where intermediary download files will be saved. Defaults to `/downloads` in the Docker image, and `.` otherwise.
  * Set this to an SSD or RAM filesystem (e.g., `tmpfs`) for better performance.
  * __Note__: Using a RAM filesystem may prevent downloads from being resumed.
* __CHOWN_DIRS__: If `false`, ownership of `DOWNLOAD_DIR`, `STATE_DIR`, and `TEMP_DIR` (and their contents) will not be set on container start. Ensure user under which MeTube runs has necessary access to these directories already. Defaults to `true`.

### 📝 File Naming & yt-dlp

* __OUTPUT_TEMPLATE__: The template for the filenames of the downloaded videos, formatted according to [this spec](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#output-template). Defaults to `%(title)s.%(ext)s`.
* __OUTPUT_TEMPLATE_CHAPTER__: The template for the filenames of the downloaded videos when split into chapters via postprocessors. Defaults to `%(title)s - %(section_number)s %(section_title)s.%(ext)s`.
* __OUTPUT_TEMPLATE_PLAYLIST__: The template for the filenames of the downloaded videos when downloaded as a playlist. Defaults to `%(playlist_title)s/%(title)s.%(ext)s`. When empty, then `OUTPUT_TEMPLATE` is used.
* __OUTPUT_TEMPLATE_CHANNEL__: The template for the filenames of the downloaded videos when downloaded as a channel. Defaults to `%(channel)s/%(title)s.%(ext)s`. When empty, then `OUTPUT_TEMPLATE` is used.
* __YTDL_OPTIONS__: Additional options to pass to yt-dlp in JSON format. [See available options here](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L222). They roughly correspond to command-line options, though some do not have exact equivalents here. For example, `--recode-video` has to be specified via `postprocessors`. Also note that dashes are replaced with underscores. You may find [this script](https://github.com/yt-dlp/yt-dlp/blob/master/devscripts/cli_to_api.py) helpful for converting from command-line options to `YTDL_OPTIONS`.
* __YTDL_OPTIONS_FILE__: A path to a JSON file that will be loaded and used for populating `YTDL_OPTIONS` above. Please note that if both `YTDL_OPTIONS_FILE` and `YTDL_OPTIONS` are specified, the options in `YTDL_OPTIONS` take precedence. The file will be monitored for changes and reloaded automatically when changes are detected.

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

The project's Wiki contains examples of useful configurations contributed by users of MeTube:
* [YTDL_OPTIONS Cookbook](https://github.com/alexta69/metube/wiki/YTDL_OPTIONS-Cookbook)
* [OUTPUT_TEMPLATE Cookbook](https://github.com/alexta69/metube/wiki/OUTPUT_TEMPLATE-Cookbook)

## 🍪 Using browser cookies

In case you need to use your browser's cookies with MeTube, for example to download restricted or private videos:

* Add the following to your docker-compose.yml:

```yaml
    volumes:
      - /path/to/cookies:/cookies
    environment:
      - YTDL_OPTIONS={"cookiefile":"/cookies/cookies.txt"}
```

* Install in your browser an extension to extract cookies:
  * [Firefox](https://addons.mozilla.org/en-US/firefox/addon/export-cookies-txt/)
  * [Chrome](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
* Extract the cookies you need with the extension and rename the file `cookies.txt`
* Drop the file in the folder you configured in the docker-compose.yml above
* Restart the container

## 🔌 Browser extensions

Browser extensions allow right-clicking videos and sending them directly to MeTube. Please note that if you're on an HTTPS page, your MeTube instance must be behind an HTTPS reverse proxy (see below) for the extensions to work.

__Chrome:__ contributed by [Rpsl](https://github.com/rpsl). You can install it from [Google Chrome Webstore](https://chrome.google.com/webstore/detail/metube-downloader/fbmkmdnlhacefjljljlbhkodfmfkijdh) or use developer mode and install [from sources](https://github.com/Rpsl/metube-browser-extension).

__Firefox:__ contributed by [nanocortex](https://github.com/nanocortex). You can install it from [Firefox Addons](https://addons.mozilla.org/en-US/firefox/addon/metube-downloader) or get sources from [here](https://github.com/nanocortex/metube-firefox-addon).

## 📱 iOS Shortcut

[rithask](https://github.com/rithask) created an iOS shortcut to send URLs to MeTube from Safari. Enter the MeTube instance address when prompted which will be saved for later use. You can run the shortcut from Safari’s share menu. The shortcut can be downloaded from [this iCloud link](https://www.icloud.com/shortcuts/66627a9f334c467baabdb2769763a1a6).

## 📱 iOS Compatibility

iOS has strict requirements for video files, requiring h264 or h265 video codec and aac audio codec in MP4 container. This can sometimes be a lower quality than the best quality available. To accommodate iOS requirements, when downloading a MP4 format you can choose "Best (iOS)" to get the best quality formats as compatible as possible with iOS requirements.

To force all downloads to be converted to an iOS-compatible codec, insert this as an environment variable: 

```yaml
  environment:
    - 'YTDL_OPTIONS={"format": "best", "exec": "ffmpeg -i %(filepath)q -c:v libx264 -c:a aac %(filepath)q.h264.mp4"}'
```

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
