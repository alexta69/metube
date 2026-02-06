#!/bin/sh

PUID="${UID:-$PUID}"
PGID="${GID:-$PGID}"

echo "Setting umask to ${UMASK}"
umask ${UMASK}
echo "Creating download directory (${DOWNLOAD_DIR}), state directory (${STATE_DIR}), and temp dir (${TEMP_DIR})"
mkdir -p "${DOWNLOAD_DIR}" "${STATE_DIR}" "${TEMP_DIR}"

if [ `id -u` -eq 0 ] && [ `id -g` -eq 0 ]; then
    if [ "${PUID}" -eq 0 ]; then
        echo "Warning: it is not recommended to run as root user, please check your setting of the PUID/PGID (or legacy UID/GID) environment variables"
    fi
    if [ "${CHOWN_DIRS:-true}" != "false" ]; then
        echo "Changing ownership of download and state directories to ${PUID}:${PGID}"
        chown -R "${PUID}":"${PGID}" /app "${DOWNLOAD_DIR}" "${STATE_DIR}" "${TEMP_DIR}"
    fi
    echo "Starting BgUtils POT Provider"
    gosu "${PUID}":"${PGID}" bgutil-pot server >/tmp/bgutil-pot.log 2>&1 &
    echo "Running MeTube as user ${PUID}:${PGID}"
    exec gosu "${PUID}":"${PGID}" python3 app/main.py
else
    echo "User set by docker; running MeTube as `id -u`:`id -g`"
    echo "Starting BgUtils POT Provider"
    bgutil-pot server >/tmp/bgutil-pot.log 2>&1 &
    exec python3 app/main.py
fi
