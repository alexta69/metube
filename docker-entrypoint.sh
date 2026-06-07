#!/bin/sh

load_env_file() {
    env_file="$1"
    if [ -f "$env_file" ]; then
        echo "Loading environment from ${env_file}"
        # shellcheck disable=SC1090
        set -a
        . "$env_file"
        set +a
    fi
}

load_env_file "/app/.env"
if [ -n "${ENV_FILE}" ]; then
    load_env_file "${ENV_FILE}"
fi

PUID="${UID:-$PUID}"
PGID="${GID:-$PGID}"

echo "Setting umask to ${UMASK}"
umask ${UMASK}
echo "Creating download directory (${DOWNLOAD_DIR}), state directory (${STATE_DIR}), and temp dir (${TEMP_DIR})"
mkdir -p "${DOWNLOAD_DIR}" "${STATE_DIR}" "${TEMP_DIR}"

do_upgrade() {
    echo "Upgrading yt-dlp to nightly channel..."
    if ! python3 -m pip --version >/dev/null 2>&1; then
        echo "pip not found; attempting ensurepip"
        python3 -m ensurepip --upgrade >/dev/null 2>&1 || true
    fi
    if ! python3 -m pip install -U --pre "yt-dlp[default,curl-cffi,deno]"; then
        echo "Warning: yt-dlp nightly upgrade failed; continuing with existing installation"
        return 1
    fi
    echo "yt-dlp nightly upgrade complete"
    return 0
}

run_supervised() {
    while true; do
        "$@" &
        child_pid=$!
        trap 'kill -TERM "$child_pid" 2>/dev/null; wait "$child_pid" 2>/dev/null' TERM INT
        wait "$child_pid"
        exit_code=$?
        trap - TERM INT
        if [ "$exit_code" -eq 42 ]; then
            echo "MeTube requested yt-dlp update restart (exit 42)"
            do_upgrade || true
            continue
        fi
        return "$exit_code"
    done
}

nightly_enabled() {
    [ -n "${YTDL_NIGHTLY_UPDATE_TIME}" ]
}

disable_nightly_for_non_root() {
    if nightly_enabled; then
        echo "YTDL_NIGHTLY_UPDATE_TIME is set but this container runs as a non-root user; nightly yt-dlp updates are not supported. Ignoring YTDL_NIGHTLY_UPDATE_TIME."
        unset YTDL_NIGHTLY_UPDATE_TIME
    fi
}

if [ `id -u` -eq 0 ] && [ `id -g` -eq 0 ]; then
    if [ "${PUID}" -eq 0 ]; then
        echo "Warning: it is not recommended to run as root user, please check your setting of the PUID/PGID (or legacy UID/GID) environment variables"
    fi
    if [ "${CHOWN_DIRS:-true}" != "false" ]; then
        echo "Changing ownership of download and state directories to ${PUID}:${PGID}"
        chown -R "${PUID}":"${PGID}" /app "${DOWNLOAD_DIR}" "${STATE_DIR}" "${TEMP_DIR}"
    fi
    if nightly_enabled; then
        echo "YTDL_NIGHTLY_UPDATE_TIME is set to ${YTDL_NIGHTLY_UPDATE_TIME}; upgrading yt-dlp on startup"
        do_upgrade || true
    fi
    echo "Starting BgUtils POT Provider"
    gosu "${PUID}":"${PGID}" bgutil-pot server >/tmp/bgutil-pot.log 2>&1 &
    echo "Running MeTube as user ${PUID}:${PGID}"
    run_supervised gosu "${PUID}":"${PGID}" python3 app/main.py
    exit $?
else
    echo "User set by docker; running MeTube as `id -u`:`id -g`"
    disable_nightly_for_non_root
    echo "Starting BgUtils POT Provider"
    bgutil-pot server >/tmp/bgutil-pot.log 2>&1 &
    run_supervised python3 app/main.py
    exit $?
fi
