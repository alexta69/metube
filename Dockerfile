FROM node:lts-alpine as builder

WORKDIR /metube
COPY ui ./
RUN npm ci && \
    node_modules/.bin/ng build --prod

FROM golang:alpine3.15 as gosu-builder

RUN apk --update --no-cache add \
    git

RUN git clone -b 1.14 --depth 1 --single-branch https://github.com/tianon/gosu /src

RUN cd /src && go build -o bin/gosu

FROM python:3.8-alpine

WORKDIR /app

COPY Pipfile* ./

ADD docker-entrypoint.sh /opt/scripts/docker-entrypoint.sh

RUN apk add --update ffmpeg && \
    apk add --update --virtual .build-deps gcc g++ musl-dev && \
    pip install --no-cache-dir pipenv && \
    pipenv install --system --deploy --clear && \
    pip uninstall pipenv -y && \
    apk add --update coreutils  shadow && \
    apk del .build-deps && \
    rm -rf /var/cache/apk/* && \
    chmod +x /opt/scripts/docker-entrypoint.sh && \
    useradd metube

COPY favicon ./favicon
COPY app ./app
COPY --from=builder /metube/dist/metube ./ui/dist/metube
COPY --from=gosu-builder /src/bin/ /bin

ENV UID=99
ENV GID=100
ENV UMASK=002

ENV DOWNLOAD_DIR /downloads
ENV STATE_DIR /downloads/.metube
VOLUME /downloads
EXPOSE 8081
ENTRYPOINT [ "/opt/scripts/docker-entrypoint.sh" ]
