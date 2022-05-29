#!/bin/sh

USER=metube

echo "---Setup Timezone to ${TZ}---"
echo "${TZ}" > /etc/timezone
echo "---Checking if UID: ${UID} matches user---"
usermod -o -u ${UID} ${USER}
echo "---Checking if GID: ${GID} matches user---"
groupmod -o -g ${GID} ${USER} > /dev/null 2>&1 ||:
usermod -g ${GID} ${USER}
echo "---Setting umask to ${UMASK}---"
umask ${UMASK}

mkdir -p ${DOWNLOAD_DIR} ${STATE_DIR}

chown -R ${UID}:${GID} /app ${DOWNLOAD_DIR} ${STATE_DIR}

gosu ${USER} python3 app/main.py