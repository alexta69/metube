#!/bin/sh

echo "You are running with user `id -u`:`id -g`"

if [ `id -u` -eq 0 ] && [ `id -g` -eq 0 ]; then
    echo "Running in New Mode"
    if [ "${UID}" -eq 0 ]; then
        echo "Waring, it is not recommended to run as root user, please check if you have set the UID environment variable"
    fi
    echo "Setting umask to ${UMASK}"
    umask ${UMASK}
    mkdir -p "${DOWNLOAD_DIR}" "${STATE_DIR}"
    chown -R "${UID}":"${GID}" /app "${DOWNLOAD_DIR}" "${STATE_DIR}"
    su-exec "${UID}":"${GID}" python3 app/main.py
else
    echo "Running in Legacy Mode"
    python3 app/main.py
fi
