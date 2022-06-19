# MeTube

![Build Status](https://github.com/alexta69/metube/actions/workflows/main.yml/badge.svg)
![Docker Pulls](https://img.shields.io/docker/pulls/alexta69/metube.svg)

Web GUI for youtube-dl (using the [yt-dlp](https://github.com/yt-dlp/yt-dlp) fork) with playlist support. Allows you to download videos from YouTube and dozens of other sites (https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).

![screenshot1](https://github.com/alexta69/metube/raw/master/screenshot.gif)

## Run using Docker

```bash
docker run -d -p 8081:8081 -v /path/to/downloads:/downloads alexta69/metube
```
## Run using docker-compose

```yaml
version: "3"
services:
  metube:
    image: alexta69/metube
    container_name: metube
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      - /path/to/downloads:/downloads
```

## Configuration via environment variables

Certain values can be set via environment variables, using the `-e` parameter on the docker command line, or the `environment:` section in docker-compose.

* __UID__: user under which MeTube will run. Defaults to `1000`.
* __GID__: group under which MeTube will run. Defaults to `1000`.
* __UMASK__: umask value used by MeTube. Defaults to `022`.
* __DOWNLOAD_DIR__: path to where the downloads will be saved. Defaults to `/downloads` in the docker image, and `.` otherwise.
* __AUDIO_DOWNLOAD_DIR__: path to where audio-only downloads will be saved, if you wish to separate them from the video downloads. Defaults to the value of `DOWNLOAD_DIR`.
* __STATE_DIR__: path to where the queue persistence files will be saved. Defaults to `/downloads/.metube` in the docker image, and `.` otherwise.
* __URL_PREFIX__: base path for the web server (for use when hosting behind a reverse proxy). Defaults to `/`.
* __OUTPUT_TEMPLATE__: the template for the filenames of the downloaded videos, formatted according to [this spec](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#output-template). Defaults to `%(title)s.%(ext)s`.
* __OUTPUT_TEMPLATE_CHAPTER__: the template for the filenames of the downloaded videos, when split into chapters via postprocessors. Defaults to `%(title)s - %(section_number)s %(section_title)s.%(ext)s`.
* __YTDL_OPTIONS__: Additional options to pass to youtube-dl, in JSON format. [See available options here](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L176). They roughly correspond to command-line options, though some do not have exact equivalents here, for example `--recode-video` has to be specified via `postprocessors`. Also note that dashes are replaced with underscores.

The following example value for `YTDL_OPTIONS` embeds English subtitles and chapter markers (for videos that have them), and also changes the permissions on the downloaded video:
```
{"writesubtitles": true, "subtitleslangs": ["en", "-live_chat"], "postprocessors": [{"key": "Exec", "exec_cmd": "chmod 0664", "when": "after_move"}, {"key": "FFmpegEmbedSubtitle", "already_have_subtitle": false}, {"key": "FFmpegMetadata", "add_chapters": true}]}
```

## Using browser cookies
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
    * [Chrome](https://chrome.google.com/webstore/detail/get-cookiestxt/bgaddhkoddajcdgocldbbfleckgcbcid) 
* Extract the cookies you need with the extension and rename the file `cookies.txt`
* Drop the file in the folder you configured in the docker-compose.yml above
* Restart the container

## Browser extensions

Browser extensions allow right-clicking videos and sending them directly to MeTube. Please note that if you're on an HTTPS page, your MeTube instance must be behind an HTTPS reverse proxy (see below) for the extensions to work.

__Chrome:__ contributed by [Rpsl](https://github.com/rpsl). You can install it from [Google Chrome Webstore](https://chrome.google.com/webstore/detail/metube-downloader/fbmkmdnlhacefjljljlbhkodfmfkijdh) or use developer mode and install [from sources](https://github.com/Rpsl/metube-browser-extension).

__Firefox:__ contributed by [nanocortex](https://github.com/nanocortex). You can install it from [Firefox Addons](https://addons.mozilla.org/en-US/firefox/addon/metube-downloader) or get sources from [here](https://github.com/nanocortex/metube-firefox-addon).

## Bookmarklet

[kushfest](https://github.com/kushfest) has created a Chrome bookmarklet for sending the currently open webpage to MeTube. Please note that if you're on an HTTPS page, your MeTube instance must be behind an HTTPS reverse proxy (see below) for the bookmarklet to work.

GitHub doesn't allow embedding JavaScript as a link, so the bookmarklet has to be created manually by copying the following code to a new bookmark you create on your bookmarks bar. Change the hostname in the URL below to point to your MeTube instance.

```javascript
javascript:!function(){xhr=new XMLHttpRequest();xhr.open("POST","https://metube.domain.com/add");xhr.send(JSON.stringify({"url":document.location.href,"quality":"best"}));xhr.onload=function(){if(xhr.status==200){alert("Sent to metube!")}else{alert("Send to metube failed. Check the javascript console for clues.")}}}();
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

## Running behind a reverse proxy

It's advisable to run MeTube behind a reverse proxy, if authentication and/or HTTPS support are required.

When running behind a reverse proxy which remaps the URL (i.e. serves MeTube under a subdirectory and not under root), don't forget to set the URL_PREFIX environment variable to the correct value.

If you're using the [linuxserver/swag](https://docs.linuxserver.io/general/swag) image for your reverse proxying needs (which I can heartily recommend), it already includes ready snippets for proxying MeTube both in [subfolder](https://github.com/linuxserver/reverse-proxy-confs/blob/master/metube.subfolder.conf.sample) and [subdomain](https://github.com/linuxserver/reverse-proxy-confs/blob/master/metube.subdomain.conf.sample) modes under the `nginx/proxy-confs` directory in the configuration volume. It also includes Authelia which can be used for authentication.

### NGINX

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

### Apache

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

### Caddy

The following example Caddyfile gets a reverse proxy going behind [caddy](https://caddyserver.com).

```caddyfile
example.com {
  route /metube/* {
    uri strip_prefix metube
    reverse_proxy metube:8081
  }
}
```

## Updating yt-dlp

The engine which powers the actual video downloads in MeTube is [yt-dlp](https://github.com/yt-dlp/yt-dlp). Since video sites regularly change their layouts, frequent updates of yt-dlp are required to keep up.

There's an automatic nightly build of MeTube which looks for a new version of yt-dlp, and if one exists, the build pulls it and publishes an updated docker image. Therefore, in order to keep up with the changes, it's recommended that you update your MeTube container regularly with the latest image.

I recommend installing and setting up [watchtower](https://github.com/containrrr/watchtower) for this purpose.

## Build and run locally

Make sure you have node.js and Python 3.8 installed.

```bash
cd metube/ui
# install Angular and build the UI
npm install
node_modules/.bin/ng build
# install python dependencies
cd ..
pip3 install pipenv
pipenv install
# run
pipenv run python3 app/main.py
```

A Docker image can be built locally (it will build the UI too):

```bash
docker build -t metube .
```

## Development notes

* The above works on Windows and macOS as well as Linux.
* If you're running the server in VSCode, your downloads will go to your user's Downloads folder (this is configured via the environment in .vscode/launch.json).
