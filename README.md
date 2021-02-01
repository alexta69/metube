# MeTube

Web GUI for youtube-dl with playlist support. Allows you to download videos from YouTube and dozens of other sites (https://ytdl-org.github.io/youtube-dl/supportedsites.html).

![screenshot1](https://github.com/alexta69/metube/raw/master/screenshot.gif)

## Run using Docker

```bash
docker run -d -p 8081:8081 -v /path/to/downloads:/downloads --user 1001:1001 alexta69/metube
```

## Run using docker-compose

```yaml
version: "3"
services:
  metube:
    image: alexta69/metube
    container_name: metube
    restart: unless-stopped
    user: "1001:1001"
    ports:
      - "8081:8081"
    volumes:
      - /path/to/downloads:/downloads
```

## Configuration via environment variables

Certain values can be set via environment variables, using the `-e` parameter on the docker command line, or the `environment:` section in docker-compose.

* __DOWNLOAD_DIR__: path to where the downloads will be saved. Defaults to `/downloads` in the docker image, and `.` otherwise.
* __URL_PREFIX__: base path for the web server (for use when hosting behind a reverse proxy). Defaults to `/`.

## Running behind a reverse proxy

Use the following nginx configuration to run MeTube behind a reverse proxy. The extra `proxy_set_header` directives are there to make WebSocket work. Don't forget to set the URL_PREFIX environment variable to the correct value as well.

```
location /metube/ {
        proxy_pass http://metube:8081;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
}
```

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
python3 app/main.py
```

A Docker image can be built locally (it will build the UI too):

```bash
docker build -t metube .
```

## Development notes

* The above works on Windows and MacOS as well as Linux.
* If you're running the server in VSCode, your downloads will go to your user's Downloads folder (this is configured via the environment in .vscode/launch.json).
