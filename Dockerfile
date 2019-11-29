FROM node as builder

WORKDIR /metube
COPY ui ./
RUN npm install && \
    node_modules/.bin/ng build --prod


FROM python:3.8-alpine

WORKDIR /app

COPY Pipfile* ./

RUN apk add --update ffmpeg && \
    apk add --update --virtual .build-deps gcc musl-dev && \
    pip install --no-cache-dir pipenv && \
    pipenv install --system --deploy --clear && \
    pip uninstall pipenv -y && \
    apk del .build-deps && \
    rm -rf /var/cache/apk/*

COPY favicon ./favicon
COPY app ./app
COPY --from=builder /metube/dist/metube ./ui/dist/metube

ENV DOWNLOAD_DIR /downloads
VOLUME /downloads
EXPOSE 8081
CMD ["python3", "app/main.py"]
