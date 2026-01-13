#!/bin/sh

echo "Setting umask to ${UMASK}"
umask ${UMASK}

DOWNLOAD_DIR_CREATED=false
if [ ! -d "${DOWNLOAD_DIR}" ]; then
    DOWNLOAD_DIR_CREATED=true
fi

echo "Creating download directory (${DOWNLOAD_DIR}), state directory (${STATE_DIR}), and temp dir (${TEMP_DIR})"
mkdir -p "${DOWNLOAD_DIR}" "${STATE_DIR}" "${TEMP_DIR}"

if [ `id -u` -eq 0 ] && [ `id -g` -eq 0 ]; then
    if [ "${UID}" -eq 0 ]; then
        echo "Warning: it is not recommended to run as root user, please check your setting of the UID environment variable"
    fi
    
    echo "Changing ownership of state directories to ${UID}:${GID}"
    chown -R "${UID}":"${GID}" /app "${STATE_DIR}" "${TEMP_DIR}"
    
    if [ "${CHOWN_DOWNLOAD_DIR:-true}" != "false" ] || [ "${DOWNLOAD_DIR_CREATED}" = "true" ]; then
        echo "Changing ownership of download directory (${DOWNLOAD_DIR})"
        chown -R "${UID}:${GID}" "${DOWNLOAD_DIR}"
    fi
    
    echo "Running MeTube as user ${UID}:${GID}"
    exec su-exec "${UID}":"${GID}" python3 app/main.py
else
    echo "User set by docker; running MeTube as `id -u`:`id -g`"
    exec python3 app/main.py
fi
