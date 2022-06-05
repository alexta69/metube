FROM node:lts-alpine as builder

WORKDIR /metube
COPY ui ./
RUN npm ci && \
    node_modules/.bin/ng build --prod

FROM python:3.8-alpine

WORKDIR /app

COPY Pipfile* ./

RUN apk add --update ffmpeg && \
    apk add --update --virtual .build-deps gcc g++ musl-dev && \
    pip install --no-cache-dir pipenv && \
    pipenv install --system --deploy --clear && \
    pip uninstall pipenv -y && \
    apk add --update coreutils shadow su-exec && \
    apk del .build-deps && \
    rm -rf /var/cache/apk/*

ADD docker-entrypoint.sh /opt/scripts/docker-entrypoint.sh
RUN chmod +x /opt/scripts/docker-entrypoint.sh

COPY favicon ./favicon
COPY app ./app
COPY --from=builder /metube/dist/metube ./ui/dist/metube

ENV UID=0
ENV GID=0
ENV UMASK=000

ENV DOWNLOAD_DIR /downloads
ENV STATE_DIR /downloads/.metube
VOLUME /downloads
EXPOSE 8081
ENTRYPOINT [ "/opt/scripts/docker-entrypoint.sh" ]
